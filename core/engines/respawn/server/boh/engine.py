# core/engines/respawn/server/boh/engine.py
from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Callable, List, Any

import cv2

from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher import match_in_zone
from core.vision.capture.window_bgr_capture import capture_window_region_bgr

from .templates import resolver as tplresolver
from .respawn_data import ZONES, TEMPLATES

Point = Tuple[int, int]
Zone = Tuple[int, int, int, int]

DEFAULT_CLICK_THRESHOLD = 0.70
DEFAULT_CONFIRM_TIMEOUT_S = 6.0

# порядок проверки шаблонов
PREFERRED_TEMPLATE_KEYS: List[str] = ["reborn_banner", "death_banner", "accept_button", "decline_button"]


class RespawnEngine:
    """
    Движок подъёма после смерти (respawn) со сканером баннеров и режимами процедуры.
    """

    def __init__(
        self,
        server: str,
        controller: Any,
        is_alive_cb: Optional[Callable[[], bool]] = None,
        click_threshold: float = DEFAULT_CLICK_THRESHOLD,
        confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
        debug: bool = False,
        on_report: Optional[Callable[[str, str], None]] = None,
    ):
        self.server = server
        self.controller = controller
        self._is_alive_cb = is_alive_cb or (lambda: True)
        self.click_threshold = float(click_threshold)
        self.confirm_timeout_s = float(confirm_timeout_s)
        self.debug = bool(debug)
        self.on_report = on_report

    # --- API ---
    def set_server(self, server: str) -> None:
        self.server = server

    def scan_banner_key(self, window: Dict, lang: str) -> Optional[Tuple[Point, str]]:
        """
        Публичный сканер: вернуть ((x,y), key) либо None без побочных эффектов.
        key ∈ {'reborn_banner','death_banner','accept_button','decline_button'}
        """
        zone_decl = ZONES.get("death_banners")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        # 1) основной путь через match_in_zone (как было раньше)
        for key in PREFERRED_TEMPLATE_KEYS:
            parts = TEMPLATES.get(key)
            if not parts:
                continue
            pt = match_in_zone(
                window=window,
                zone_ltrb=ltrb,
                server=self.server,
                lang=(lang or "rus").lower(),
                template_parts=parts,
                threshold=self.click_threshold,
                engine="respawn",
            )
            if pt is not None:
                return (pt, key)

        # 2) fallback на чистом OpenCV, если основной поиск не нашёл
        fb = self._fallback_scan(window, (lang or "rus").lower(), ltrb)
        if fb is not None:
            return fb

        return None

    def run_procedure(
        self,
        window: Dict,
        lang: str,
        mode: str = "auto",            # "wait_reborn" | "to_village" | "auto"
        wait_seconds: int = 0,         # используется для "wait_reborn"
        total_timeout_ms: int = 14_000 # защита от зацикливания
    ) -> bool:
        """
        Высокоуровневая процедура согласно ТЗ. Шлёт репорты on_report(...).
        """
        mode = (mode or "auto").lower()
        lang = (lang or "rus").lower()
        self._report("BANNERS_SCAN_START", "Ищу баннеры (death/reborn)…")

        # мгновенная победа, если уже живы
        if self._is_alive():
            self._report("ALIVE_OK", "Поднялись (hp > 0)")
            self._report("SUCCESS", "Успешно восстановились")
            return True

        start_ts = time.time()
        deadline = start_ts + max(1, int(total_timeout_ms)) / 1000.0

        # Лямбда для одношагового активного подъёма
        def _active_standup() -> bool:
            ok = self.run_stand_up_once(window, lang, timeout_ms=int(max(1000, (deadline - time.time()) * 1000)))
            return bool(ok)

        # --- режим: to_village — ждём именно death_banner, иначе FAIL
        if mode == "to_village":
            found = self.scan_banner_key(window, lang)
            if not found or found[1] != "death_banner":
                self._report("NO_BANNERS", "Баннеры не найдены")
                self._report("FAIL", "Не удалось подняться")
                return False
            return _active_standup()

        # --- режим: wait_reborn — до wait_seconds тикаем и сканируем
        if mode == "wait_reborn":
            wait_seconds = max(0, int(wait_seconds or 0))
            tick = 0
            while time.time() < deadline:
                if self._is_alive():
                    self._report("ALIVE_OK", "Поднялись (hp > 0)")
                    self._report("SUCCESS", "Успешно восстановились")
                    return True

                # тикер для UI (раз в сек)
                now = time.time()
                elapsed = int(now - start_ts)
                if elapsed > tick and elapsed <= wait_seconds:
                    tick = elapsed
                    self._report("WAIT_TICK", f"Ожидание возрождения… {tick}/{wait_seconds} сек")

                # попробуем найти баннер и сразу активироваться
                fb = self.scan_banner_key(window, lang)
                if fb is not None:
                    key = fb[1]
                    if key == "death_banner":
                        self._report("BANNER_FOUND:DEATH", "Нашёл death_banner")
                    elif key == "reborn_banner":
                        self._report("BANNER_FOUND:REBORN", "Нашёл reborn_banner")
                    ok = _active_standup()
                    if ok:
                        self._report("SUCCESS", "Успешно восстановились")
                        return True
                    else:
                        self._report("FAIL", "Не удалось подняться")
                        return False

                if elapsed >= wait_seconds:
                    self._report("TIMEOUT:WAIT_REBORN", "Истёк лимит ожидания возрождения")
                    self._report("NO_BANNERS", "Баннеры не найдены")
                    self._report("FAIL", "Не удалось подняться")
                    return False

                time.sleep(0.2)

            # общий дедлайн
            self._report("FAIL", "Не удалось подняться")
            return False

        # --- режим: auto — короткое ожидание (3–5 c), иначе FAIL
        if mode == "auto":
            soft_deadline = time.time() + 4.0
            while time.time() < min(soft_deadline, deadline):
                if self._is_alive():
                    self._report("ALIVE_OK", "Поднялись (hp > 0)")
                    self._report("SUCCESS", "Успешно восстановились")
                    return True
                fb = self.scan_banner_key(window, lang)
                if fb is not None:
                    key = fb[1]
                    if key == "death_banner":
                        self._report("BANNER_FOUND:DEATH", "Нашёл death_banner")
                    elif key == "reborn_banner":
                        self._report("BANNER_FOUND:REBORN", "Нашёл reborn_banner")
                    ok = _active_standup()
                    if ok:
                        self._report("SUCCESS", "Успешно восстановились")
                        return True
                    else:
                        self._report("FAIL", "Не удалось подняться")
                        return False
                time.sleep(0.2)

            self._report("NO_BANNERS", "Баннеры не найдены")
            self._report("FAIL", "Не удалось подняться")
            return False

        # неизвестный режим → ведём себя как auto
        return self.run_procedure(window, lang, mode="auto", wait_seconds=0, total_timeout_ms=int((deadline - time.time()) * 1000))

    def run_stand_up_once(self, window: Dict, lang: str, timeout_ms: int = 14_000) -> bool:
        """Активный подъём: кликаем по найденному баннеру до исчезновения/оживления."""
        self._report("BANNERS_SCAN_START", "Ищу баннеры (death/reborn)…")

        # фокус окна
        try:
            if hasattr(self.controller, "focus") and window:
                self.controller.focus(window)
        except Exception:
            pass

        total_deadline = time.time() + max(1, int(timeout_ms)) / 1000.0

        ok = self._click_until_alive_or_banner_gone(window, lang, total_deadline)
        if ok is True:
            self._report("SUCCESS", "Успешно восстановились")
            return True
        if ok is False:
            self._report("FAIL", "Не удалось подняться")
            return False

        # баннер исчез — ждём загрузку
        load_deadline = time.time() + 10.0
        while time.time() < load_deadline:
            if self._is_alive():
                self._log("[respawn] alive during loading wait")
                self._report("ALIVE_OK", "Поднялись (hp > 0)")
                self._report("SUCCESS", "Успешно восстановились")
                return True
            res = self._find_banner(window, lang)  # без репорта
            if res is not None:
                ok2 = self._click_until_alive_or_banner_gone(window, lang, load_deadline)
                if ok2 is True:
                    self._report("SUCCESS", "Успешно восстановились")
                    return True
                if ok2 is False:
                    self._report("FAIL", "Не удалось подняться")
                    return False
            time.sleep(0.1)

        self._log("[respawn] fallback: still not alive and no banner")
        self._report("NO_BANNERS", "Баннеры не найдены")
        self._report("FAIL", "Не удалось подняться")
        return False

    # совместимость
    def run_to_village_once(self, window: Dict, lang: str, timeout_ms: int = 14_000) -> bool:
        return self.run_stand_up_once(window, lang, timeout_ms)

    # --- internals ---
    def _find_banner(self, win: Dict, lang: str) -> Optional[Tuple[Point, str]]:
        """Внутренний вариант: без репортов."""
        return self.scan_banner_key(win, lang)

    def _banner_with_report(self, win: Dict, lang: str) -> Optional[Tuple[Point, str]]:
        """Скан с репортами BANNER_FOUND:* при успехе."""
        res = self._find_banner(win, lang)
        if res is not None:
            _, key = res
            if key == "death_banner":
                self._report("BANNER_FOUND:DEATH", "Нашёл death_banner")
            elif key == "reborn_banner":
                self._report("BANNER_FOUND:REBORN", "Нашёл reborn_banner")
        return res

    def _click(self, x: int, y: int, delay_s: float = 0.40) -> None:
        try:
            if hasattr(self.controller, "move"):
                self.controller.move(int(x), int(y))
            time.sleep(max(0.0, float(delay_s)))
            if hasattr(self.controller, "_click_left_arduino"):
                self.controller._click_left_arduino()
            else:
                self.controller.send("l")
        except Exception:
            pass

    def _is_alive(self) -> bool:
        try:
            return bool(self._is_alive_cb())
        except Exception:
            return True

    def _click_until_alive_or_banner_gone(self, win: Dict, lang: str, phase_deadline: float) -> Optional[bool]:
        last_click_ts = 0.0
        last_seen_key: Optional[str] = None

        while time.time() < phase_deadline:
            if self._is_alive():
                self._log("[respawn] alive detected")
                self._report("ALIVE_OK", "Поднялись (hp > 0)")
                return True

            res = self._banner_with_report(win, lang)
            if res is None:
                # баннер исчез
                if last_seen_key == "death_banner":
                    self._report("BANNER_GONE:DEATH", "Death_banner исчез — ждём загрузку")
                elif last_seen_key == "reborn_banner":
                    self._report("BANNER_GONE:REBORN", "Reborn баннер исчез — ждём подъёма")
                return None

            (pt, key) = res
            last_seen_key = key

            now = time.time()
            if now - last_click_ts >= 0.6:
                self._log(f"[respawn] click @ {pt[0]},{pt[1]}")
                if key == "death_banner":
                    self._report("CLICK:DEATH", "Клик по death_banner")
                elif key == "reborn_banner":
                    self._report("CLICK:REBORN_ACCEPT", "Клик по кнопке согласия (reborn)")
                self._click(pt[0], pt[1])
                last_click_ts = now

                confirm_deadline = now + self.confirm_timeout_s
                while time.time() < confirm_deadline:
                    if self._is_alive():
                        self._log("[respawn] alive after click")
                        self._report("ALIVE_OK", "Поднялись (hp > 0)")
                        return True
                    if self._find_banner(win, lang) is None:
                        if key == "death_banner":
                            self._report("BANNER_GONE:DEATH", "Death_banner исчез — ждём загрузку")
                        elif key == "reborn_banner":
                            self._report("BANNER_GONE:REBORN", "Reborn баннер исчез — ждём подъёма")
                        return None
                    time.sleep(0.05)

                self._report("TIMEOUT:CONFIRM", "Таймаут подтверждения после клика")

            time.sleep(0.05)

        self._log("[respawn] phase deadline reached with banner visible")
        self._report("FAIL", "Не удалось подняться")
        return False

    # ---- Fallback OpenCV scan ----
    def _fallback_scan(self, window: Dict, lang: str, ltrb: Tuple[int, int, int, int]) -> Optional[Tuple[Point, str]]:
        """
        Универсальный запасной поиск по всем ключам из PREFERRED_TEMPLATE_KEYS
        через cv2.matchTemplate с несколькими масштабами.
        """
        img = capture_window_region_bgr(window, ltrb)
        if img is None or img.size == 0:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        best = None  # {'score': float, 'loc': (x,y), 'w': int, 'h': int, 'key': str}
        scales = (1.0, 0.9, 1.1, 0.8, 1.2)

        for key in PREFERRED_TEMPLATE_KEYS:
            parts = TEMPLATES.get(key)
            if not parts:
                continue
            path = tplresolver.resolve(lang, *parts)
            if not path:
                if self.debug:
                    print(f"[respawn/fallback] no template for key={key} lang={lang}")
                continue

            tpl = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if tpl is None or tpl.size == 0:
                if self.debug:
                    print(f"[respawn/fallback] failed to read: {path}")
                continue

            for s in scales:
                tw = max(1, int(round(tpl.shape[1] * s)))
                th = max(1, int(round(tpl.shape[0] * s)))
                t = cv2.resize(
                    tpl,
                    (tw, th),
                    interpolation=cv2.INTER_AREA if s < 1.0 else cv2.INTER_CUBIC
                )
                if t.shape[0] > gray.shape[0] or t.shape[1] > gray.shape[1]:
                    continue

                res = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
                _, maxVal, _, maxLoc = cv2.minMaxLoc(res)
                score = float(maxVal)
                if best is None or score > best['score']:
                    best = {'score': score, 'loc': maxLoc, 'w': t.shape[1], 'h': t.shape[0], 'key': key}

        if best and best['score'] >= self.click_threshold:
            zl, zt, _, _ = ltrb
            # центр найденного шаблона в КЛИЕНТСКИХ координатах
            cx_client = zl + best['loc'][0] + best['w'] // 2
            cy_client = zt + best['loc'][1] + best['h'] // 2
            # преобразуем в ЭКРАННЫЕ координаты
            win_x = int(window.get("x", 0))
            win_y = int(window.get("y", 0))
            cx_screen = win_x + cx_client
            cy_screen = win_y + cy_client

            if self.debug:
                print(f"[respawn/fallback] {best['key']} score={best['score']:.3f} @ ({cx_screen},{cy_screen})")

            return ((cx_screen, cy_screen), best['key'])

    # ---- util ----
    def _log(self, msg: str):
        if self.debug:
            try:
                print(msg)
            except Exception:
                pass

    def _report(self, code: str, text: str):
        if callable(self.on_report):
            try:
                self.on_report(code, text)
            except Exception:
                pass
