from __future__ import annotations
import time
import os
from typing import Optional, Dict, Tuple, Callable, List, Any

from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher_2 import match_key_in_zone_single
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

    def scan_banner_key(
        self,
        window: Dict,
        lang: str,
        allowed_keys: Optional[List[str]] = None,
    ) -> Optional[Tuple[Point, str]]:
        """
        Последовательный ТОЧЕЧНЫЙ поиск по ключам (как в бафере):
        для каждого key → match_key_in_zone_single → при успехе вернуть (pt, key).
        Для reborn предпочитаем клик именно по accept_button.
        """
        # Зона: компактная центральная, если задана, иначе весь экран
        zone_decl = ZONES.get("death_banners") or ZONES.get("fullscreen")
        if not zone_decl or not window:
            return None
        ltrb = compute_zone_ltrb(window, zone_decl)

        if self._debug_enabled():
            console.log(f"[RESPAWN/DBG] scan LTRB={ltrb} thr={self.click_threshold:.2f}")

        keys = list(allowed_keys) if allowed_keys else list(PREFERRED_TEMPLATE_KEYS)
        lang = (lang or "rus").lower()

        # Диагностика наличия файлов шаблонов
        if self._debug_enabled():
            for k in keys:
                parts = TEMPLATES.get(k)
                if not parts:
                    self._dbg(f"нет parts для ключа '{k}'")
                    continue
                p = tplresolver.resolve(lang, *parts)
                if not p:
                    self._dbg(f"не найден файл шаблона для '{k}' (lang={lang})")

        for key in keys:
            parts = TEMPLATES.get(key)
            if not parts:
                continue
            pt = match_key_in_zone_single(
                window=window,
                zone_ltrb=ltrb,
                server=self.server,
                lang=lang,
                template_parts=parts,
                threshold=self.click_threshold,
                engine="respawn",
            )
            if pt:
                # Если видим окно реса — попробуем кликнуть по accept_button
                if key == "reborn_banner":
                    acc = self.find_key_in_zone(window, lang, "accept_button")
                    if acc:
                        return (acc, "accept_button")
                return (pt, key)

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
