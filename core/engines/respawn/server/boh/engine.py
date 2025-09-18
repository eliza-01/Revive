# core/engines/respawn/server/boh/engine.py
from __future__ import annotations
import time
import os
from typing import Optional, Dict, Tuple, Callable, List, Any

from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher_2 import match_multi_in_zone, match_key_in_zone_single

from .respawn_data import ZONES, TEMPLATES
from .templates import resolver as tplresolver
from core.logging import console
from core.state.pool import pool_get

Point = Tuple[int, int]

# Порог и таймаут по умолчанию
DEFAULT_CLICK_THRESHOLD = 0.70
DEFAULT_CONFIRM_TIMEOUT_S = 6.0

REVIVE_RESPAWN_DEBUG = 0

# Базовый порядок (если allowed_keys не задан)
PREFERRED_TEMPLATE_KEYS: List[str] = [
    "reborn_banner",
    "accept_button",
    "death_banner",
    "decline_button",
]


class RespawnEngine:
    """
    Низкоуровневый движок: последовательный точечный поиск по ключам (как в бафере).
    Вся сценарная логика — в rules.py.
    """

    def __init__(
        self,
        *,
        server: str,
        controller: Any,
        is_alive_cb: Optional[Callable[[], bool]] = None,
        click_threshold: float = DEFAULT_CLICK_THRESHOLD,
        confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
    ):
        self.server = (server or "").lower()
        self.controller = controller
        self._is_alive_cb = is_alive_cb or (lambda: True)
        self.click_threshold = float(click_threshold)
        self.confirm_timeout_s = float(confirm_timeout_s)

    # ---- debug ----
    def _debug_enabled(self) -> bool:
        """
        Включаем отладку ТОЛЬКО при явном True в пуле:
        runtime.debug.respawn_debug == True
        """
        try:
            env = os.getenv("REVIVE_RESPAWN_DEBUG", "")
            if env.strip().lower() in ("1", "true", "yes", "on"):
                return True
            st = getattr(self.controller, "_state", None)
            if isinstance(st, dict):
                return pool_get(st, "runtime.debug.respawn_debug", False) is True
        except Exception:
            pass
        return False

    def _dbg(self, msg: str) -> None:
        try:
            if self._debug_enabled():
                console.log(f"[RESPAWN/DBG] {msg}")
        except Exception:
            pass

    # ---- helpers ----
    def _is_alive(self) -> bool:
        try:
            return bool(self._is_alive_cb())
        except Exception:
            return True

    # ---- API ----
    def set_server(self, server: str) -> None:
        self.server = (server or "").lower()

    # --- ВСТАВИТЬ ВМЕСТО ТЕКУЩЕГО scan_banner_key ---
    def scan_banner_key(
            self,
            window: Dict,
            lang: str,
            allowed_keys: Optional[List[str]] = None,
    ) -> Optional[Tuple[Point, str]]:
        """
        Скан разрешённых ключей. Сначала пробуем мульти-матчер,
        затем фолбэк: точечный поиск death_banner (to_village_button.png).
        """
        zone_decl = ZONES.get("death_banners") or ZONES.get("fullscreen")
        if not zone_decl or not window:
            self._dbg("scan: no window/zone")
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        # порядок: death сначала (если не передали свой)
        key_order = list(allowed_keys) if allowed_keys else ["death_banner", "reborn_banner", "accept_button"]
        L = (lang or "rus").lower()

        # отладка путей (без переменных, которых нет → чтобы не падало)
        if self._debug_enabled():
            self._dbg(f"scan: LTRB={ltrb} thr={self.click_threshold:.2f} keys={key_order}")
            for k in key_order:
                parts = TEMPLATES.get(k)
                if not parts:
                    self._dbg(f"scan: no parts for '{k}'")
                    continue
                p = tplresolver.resolve(L, *parts)
                self._dbg(f"scan: resolve[{k}] -> {p or 'None'}")

        # «разогрев» (без рескейла), чтобы гарантировать захват ROI и резолвер
        try:
            _ = match_multi_in_zone(
                window=window,
                zone_ltrb=ltrb,
                server=self.server,
                lang=L,
                templates_map=TEMPLATES,
                key_order=key_order,
                threshold=0.01,
                engine="respawn",
                scales=(1.0,),
                debug=False,
            )
        except Exception:
            pass

        # основной матч — мульти-масштаб
        res = match_multi_in_zone(
            window=window,
            zone_ltrb=ltrb,
            server=self.server,
            lang=L,
            templates_map=TEMPLATES,
            key_order=key_order,
            threshold=self.click_threshold,
            engine="respawn",
            scales=(1.0, 0.95, 1.05, 0.90, 1.10),
            debug=self._debug_enabled(),
        )
        if res:
            return res

        # фолбэк: если death_banner был разрешён — пробуем одиночный матч
        if "death_banner" in key_order and TEMPLATES.get("death_banner"):
            pt = match_key_in_zone_single(
                window=window,
                zone_ltrb=ltrb,
                server=self.server,
                lang=L,
                template_parts=TEMPLATES["death_banner"],
                threshold=self.click_threshold,
                engine="respawn",
            )
            if pt:
                return (pt, "death_banner")

        return None

    def find_key_in_zone(
        self, window: Dict, lang: str, key: str
    ) -> Optional[Tuple[int, int]]:
        """
        Точный поиск ОДНОГО ключа → экранные координаты центра или None.
        """
        zone_decl = ZONES.get("death_banners") or ZONES.get("fullscreen")
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
        self._dbg("start: ищу баннеры (death/reborn)…")
        console.hud("ok", "[respawn] Жду кнопку в город или рес")

        # фокус
        try:
            if hasattr(self.controller, "focus") and window:
                self.controller.focus(window)
        except Exception:
            pass

        zone_decl = ZONES.get("death_banners")
        if not zone_decl or not window:
            self._dbg("no window/zone (death_banners) — abort")
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
                self._dbg("alive>0 — поднялись")
                console.hud("succ", "[respawn] Возродились")
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
                debug=self._debug_enabled(),
            )

            if res is None:
                # Баннер исчез — ждём загрузку/подъём чуть-чуть
                if last_seen_key == "death_banner":
                    self._dbg("death_banner исчез → ждём загрузку")
                    console.hud("ok", "[respawn] кнопка пропала. Ждём подъём")
                elif last_seen_key == "reborn_banner":
                    self._dbg("reborn баннер исчез → ждём подъёма")
                    console.hud("ok", "[respawn] окно реса пропало. Ждём подъём")
                load_deadline = time.time() + 2.0
                while time.time() < load_deadline:
                    if self._is_alive():
                        self._dbg("alive>0 после исчезновения баннера — ок")
                        console.hud("succ", "[respawn] Возродились")
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
                self._dbg("click: reborn accept")
                console.hud("ok", "[respawn] соглашаемся на рес")
                confirm_wait_s = 5.0
            elif key == "death_banner":
                self._dbg("click: death_banner")
                console.hud("ok", "[respawn] встаём в город")

            _click(click_x, click_y)
            last_click_ts = now

            # ожидание подтверждения
            confirm_deadline = now + float(confirm_wait_s)
            while time.time() < confirm_deadline:
                if self._is_alive():
                    self._dbg("alive>0 после клика — ок")
                    console.hud("succ", "[respawn] Возродились")
                    return True
                # если баннер исчез — отдаём управление наверх
                res2 = match_multi_in_zone(
                    window=window,
                    zone_ltrb=ltrb,
                    server=self.server,
                    lang=(lang or "rus").lower(),
                    templates_map=TEMPLATES,
                    key_order=keys_for_phase,
                    threshold=self.click_threshold,
                    engine="respawn",
                    debug=self._debug_enabled(),
                )
                if res2 is None:
                    if key == "death_banner":
                        self._dbg("death_banner пропал после клика — ждём загрузку")
                        console.hud("ok", "[respawn] кнопка пропала. Ждём подъём")
                    elif key == "reborn_banner":
                        self._dbg("reborn пропал после клика — ждём подъёма")
                        console.hud("ok", "[respawn] окно реса пропало. Ждём подъём")
                    break
                time.sleep(0.05)

            self._dbg("timeout confirm — продолжаю цикл")
            time.sleep(0.05)

        self._dbg("fail: не удалось подняться")
        console.hud("err", "[respawn] не удалось подняться")
        return False

    def pick_click_point_for_key(
        self,
        window: Dict,
        lang: str,
        key: str,
        fallback_pt: Tuple[int, int],
    ) -> Tuple[int, int]:
        """
        Для reborn_banner пытается найти accept_button и вернуть его центр,
        иначе — вернёт fallback_pt. Для остальных ключей — просто fallback_pt.
        """
        if key == "reborn_banner":
            acc = self.find_key_in_zone(window, lang, "accept_button")
            if acc is not None:
                return acc
        return fallback_pt

    def click_at(self, x: int, y: int, delay_s: float = 0.40) -> None:
        try:
            if hasattr(self.controller, "move"):
                self.controller.move(int(x), int(y))
            time.sleep(max(0.0, float(delay_s)))
            if hasattr(self.controller, "_click_left_arduino"):
                self._dbg(f"click arduino @ {x},{y}")
                self.controller._click_left_arduino()
            else:
                self._dbg(f"click send(l) @ {x},{y}")
                self.controller.send("l")
        except Exception:
            pass


def create_engine(
    *,
    server: str,
    controller: Any,
    is_alive_cb: Optional[Callable[[], bool]] = None,
    click_threshold: float = DEFAULT_CLICK_THRESHOLD,
    confirm_timeout_s: float = DEFAULT_CONFIRM_TIMEOUT_S,
) -> RespawnEngine:
    return RespawnEngine(
        server=server,
        controller=controller,
        is_alive_cb=is_alive_cb,
        click_threshold=click_threshold,
        confirm_timeout_s=confirm_timeout_s,
    )
