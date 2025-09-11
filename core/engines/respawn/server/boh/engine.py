from __future__ import annotations
import time
from typing import Optional, Dict, Tuple, Callable, List, Any

from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher_2 import (
    match_multi_in_zone,
    match_key_in_zone_single,
)
from .respawn_data import ZONES, TEMPLATES
from .templates import resolver as tplresolver

Point = Tuple[int, int]

# Снизил порог — чтобы исключить «ложную неудачу», когда картинки почти одинаковые
DEFAULT_CLICK_THRESHOLD = 0.70
DEFAULT_CONFIRM_TIMEOUT_S = 6.0

# Базовый порядок (если allowed_keys не задан)
PREFERRED_TEMPLATE_KEYS: List[str] = [
    "reborn_banner",
    "death_banner",
    "accept_button",
    "decline_button",
]


class RespawnEngine:
    """
    Низкоуровневый движок: скан разрешённых ключей и клик.
    Вся сценарная логика — в rules.py.
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

    # ---- API ----

    def set_server(self, server: str) -> None:
        self.server = server

    def _report(self, code: str, text: str):
        if callable(self.on_report):
            try:
                self.on_report(code, text)
            except Exception:
                pass

    def _is_alive(self) -> bool:
        try:
            return bool(self._is_alive_cb())
        except Exception:
            return True

    def scan_banner_key(
        self,
        window: Dict,
        lang: str,
        allowed_keys: Optional[List[str]] = None,
    ) -> Optional[Tuple[Point, str]]:
        """
        Вернуть ((x,y), key) по разрешённым ключам или None.
        Во время отладки печатаем, если шаблон не резолвится.
        """
        zone_decl = ZONES.get("death_banners")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        key_order = list(allowed_keys) if allowed_keys else list(PREFERRED_TEMPLATE_KEYS)

        # Диагностика: проверим, что пути к шаблонам реально есть
        if self.debug:
            for k in key_order:
                parts = TEMPLATES.get(k)
                if not parts:
                    self._report("TPL_MISS", f"нет parts для ключа '{k}'")
                    continue
                p = tplresolver.resolve((lang or "rus").lower(), *parts)
                if not p:
                    self._report("TPL_MISS", f"не найден файл шаблона для '{k}' (lang={lang})")

        return match_multi_in_zone(
            window=window,
            zone_ltrb=ltrb,
            server=self.server,
            lang=(lang or "rus").lower(),
            templates_map=TEMPLATES,
            key_order=key_order,
            threshold=self.click_threshold,
            engine="respawn",
            debug=self.debug,
        )

    def find_key_in_zone(
        self, window: Dict, lang: str, key: str
    ) -> Optional[Tuple[int, int]]:
        """
        Точный поиск одного ключа → экранные координаты центра или None.
        """
        zone_decl = ZONES.get("death_banners")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        parts = TEMPLATES.get(key)
        if not parts:
            return None

        return match_key_in_zone_single(
            window=window,
            zone_ltrb=ltrb,
            server=self.server,
            lang=(lang or "rus").lower(),
            template_parts=parts,
            threshold=self.click_threshold,
            engine="respawn",
        )

    def run_stand_up_once(
        self,
        window: Dict,
        lang: str,
        timeout_ms: int = 14_000,
        allowed_keys: Optional[List[str]] = None,
    ) -> bool:
        """
        ОДНА активная фаза:
          - фокус окна
          - цикл: скан разрешённых ключей, клик, ожидание alive/исчезновения
          - если баннер исчез — краткое ожидание подгрузки
        """
        self._report("BANNERS_SCAN_START", "Ищу баннеры (death/reborn)…")

        # фокус
        try:
            if hasattr(self.controller, "focus") and window:
                self.controller.focus(window)
        except Exception:
            pass

        zone_decl = ZONES.get("death_banners")
        if not zone_decl or not window:
            self._report("NO_WINDOW", "Окно/зона не заданы")
            return False
        ltrb = compute_zone_ltrb(window, zone_decl)

        total_deadline = time.time() + max(1, int(timeout_ms)) / 1000.0
        last_seen_key: Optional[str] = None
        last_click_ts = 0.0

        def _click(x: int, y: int, delay_s: float = 0.40) -> None:
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

        keys_for_phase = (allowed_keys or PREFERRED_TEMPLATE_KEYS)

        while time.time() < total_deadline:
            if self._is_alive():
                self._report("ALIVE_OK", "Поднялись (hp > 0)")
                self._report("SUCCESS", "Успешно восстановились")
                return True

            res = match_multi_in_zone(
                window=window,
                zone_ltrb=ltrb,
                server=self.server,
                lang=(lang or "rus").lower(),
                templates_map=TEMPLATES,
                key_order=keys_for_phase,
                threshold=self.click_threshold,
                engine="respawn",
                debug=self.debug,
            )

            if res is None:
                # Баннер исчез — ждём загрузку
                if last_seen_key == "death_banner":
                    self._report("BANNER_GONE:DEATH", "Death_banner исчез — ждём загрузку")
                elif last_seen_key == "reborn_banner":
                    self._report("BANNER_GONE:REBORN", "Reborn баннер исчез — ждём подъёма")
                # короткая пауза и проверка alive
                load_deadline = time.time() + 2.0
                while time.time() < load_deadline:
                    if self._is_alive():
                        self._report("ALIVE_OK", "Поднялись (hp > 0)")
                        self._report("SUCCESS", "Успешно восстановились")
                        return True
                    time.sleep(0.05)
                time.sleep(0.05)
                continue

            (pt, key) = res
            last_seen_key = key

            now = time.time()
            if now - last_click_ts < 0.6:
                time.sleep(0.05)
                continue

            click_x, click_y = pt
            confirm_wait_s = self.confirm_timeout_s

            if key == "reborn_banner":
                acc = self.find_key_in_zone(window, lang, "accept_button")
                if acc is not None:
                    click_x, click_y = acc
                self._report("CLICK:REBORN_ACCEPT", "Клик по кнопке согласия (reborn)")
                confirm_wait_s = 5.0
            elif key == "death_banner":
                self._report("CLICK:DEATH", "Клик по death_banner")

            _click(click_x, click_y)
            last_click_ts = now

            confirm_deadline = now + float(confirm_wait_s)
            while time.time() < confirm_deadline:
                if self._is_alive():
                    self._report("ALIVE_OK", "Поднялись (hp > 0)")
                    self._report("SUCCESS", "Успешно восстановились")
                    return True
                # если баннер исчез — отдаём управление наверх (цикл сам решит)
                res2 = match_multi_in_zone(
                    window=window,
                    zone_ltrb=ltrb,
                    server=self.server,
                    lang=(lang or "rus").lower(),
                    templates_map=TEMPLATES,
                    key_order=keys_for_phase,
                    threshold=self.click_threshold,
                    engine="respawn",
                    debug=self.debug,
                )
                if res2 is None:
                    if key == "death_banner":
                        self._report("BANNER_GONE:DEATH", "Death_banner исчез — ждём загрузку")
                    elif key == "reborn_banner":
                        self._report("BANNER_GONE:REBORN", "Reborn баннер исчез — ждём подъёма")
                    break
                time.sleep(0.05)

            self._report("TIMEOUT:CONFIRM", "Таймаут подтверждения после клика")
            time.sleep(0.05)

        self._report("FAIL", "Не удалось подняться")
        return False


def create_engine(
    *,
    server: str,
    controller: Any,
    is_alive_cb: Optional[Callable[[], bool]] = None,
    click_threshold: float = DEFAULT_CLICK_THRESHOLD,
    confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
    debug: bool = False,
    on_report: Optional[Callable[[str, str], None]] = None,
) -> RespawnEngine:
    return RespawnEngine(
        server=server,
        controller=controller,
        is_alive_cb=is_alive_cb,
        click_threshold=click_threshold,
        confirm_timeout_s=confirm_timeout_s,
        debug=debug,
        on_report=on_report,
    )
