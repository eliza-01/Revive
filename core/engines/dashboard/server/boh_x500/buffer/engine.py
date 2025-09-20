# core/engines/dashboard/server/boh_x500/buffer/engine.py
# core/engines/dashboard/server/<server>/buffer/engine.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, List

from core.state.pool import pool_get  # (not used now, kept only if other imports rely; can be removed)
from core.vision.zones import compute_zone_ltrb
from core.vision.matching.template_matcher_2 import (
    match_key_in_zone_single,
    match_multi_in_zone,
)

# server-local data (без хардкода имени сервера в пути)
from ..dashboard_data import TEMPLATES, ZONES, BUFFS, DANCES, SONGS


class BufferEngine:
    """
    Низкоуровневые операции вкладки Buffer:
      - клик по плитке режима (profile/fighter/mage/archer*)
      - проверка бафов по иконкам (features.buff.checker) в зоне ZONES['current_buffs']
      - (опц.) клик Restore HP

    Движок «немой»: не читает пул и не пишет в HUD. Вся сценарная логика — в rules.py.
    """

    def __init__(self, server: str, controller: Any, get_window, get_language):
        self.server = (server or "").lower()
        self.controller = controller
        self.get_window = get_window
        self.get_language = get_language

    # --- utils -------------------------------------------------------------

    def _lang(self) -> str:
        try:
            return (self.get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _win(self) -> Optional[Dict[str, Any]]:
        try:
            return self.get_window() or None
        except Exception:
            return None

    def _zone_ltrb(self, win: Dict[str, Any], name: str) -> Tuple[int, int, int, int]:
        decl = ZONES.get(name, ZONES.get("fullscreen", {"fullscreen": True}))
        l, t, r, b = compute_zone_ltrb(win, decl)
        return (int(l), int(t), int(r), int(b))

    def _click(self, x: int, y: int, *, hover_delay_s: float = 0.20, post_delay_s: float = 0.20) -> None:
        try:
            if hasattr(self.controller, "move"):
                self.controller.move(int(x), int(y))
            import time as _t
            _t.sleep(max(0.0, float(hover_delay_s)))
            if hasattr(self.controller, "_click_left_arduino"):
                self.controller._click_left_arduino()
            else:
                # стандартный левый клик через микроконтроллер (совместимо с respawn)
                self.controller.send("l")
            _t.sleep(max(0.0, float(post_delay_s)))
        except Exception:
            pass

    # --- state ------------------------------------------------------------

    def is_open(self, thr: float = 0.87) -> bool:
        """Считаем вкладку Buffer «открытой», если виден ключ 'dashboard_buffer_init'."""
        win = self._win()
        if not win:
            return False
        parts = TEMPLATES.get("dashboard_buffer_init")
        if not parts:
            return False
        pt = match_key_in_zone_single(
            window=win,
            zone_ltrb=self._zone_ltrb(win, "fullscreen"),
            server=self.server,
            lang=self._lang(),
            template_parts=parts,
            threshold=thr,
            engine="dashboard",
        )
        return pt is not None

    # --- actions ----------------------------------------------------------

    def click_mode(self, mode: str, thr: float = 0.87) -> bool:
        """
        Клик по плитке режима. Если нет точного — пробуем profile как фолбэк.
        Поиск — как в respawn: сначала матч (без клика), затем явный клик контроллером.
        """
        win = self._win()
        if not win:
            return False

        mode = (mode or "profile").strip().lower()
        candidates: List[str] = [f"dashboard_buffer_{mode}"]
        if mode != "profile":
            candidates.append("dashboard_buffer_profile")

        lang = self._lang()
        for key in candidates:
            parts = TEMPLATES.get(key)
            if not parts:
                continue
            pt = match_key_in_zone_single(
                window=win,
                zone_ltrb=self._zone_ltrb(win, "fullscreen"),
                server=self.server,
                lang=lang,
                template_parts=parts,
                threshold=thr,
                engine="dashboard",
            )
            if pt:
                x, y = pt
                self._click(x, y, hover_delay_s=0.20, post_delay_s=0.20)
                return True

        return False

    def click_restore_hp(self, thr: float = 0.85) -> bool:
        """Клик по кнопке Restore HP (если есть шаблон). Поиск как в respawn, клик явный."""
        win = self._win()
        if not win:
            return False
        parts = TEMPLATES.get("dashboard_buffer_restoreHp")
        if not parts:
            return False
        pt = match_key_in_zone_single(
            window=win,
            zone_ltrb=self._zone_ltrb(win, "fullscreen"),
            server=self.server,
            lang=self._lang(),
            template_parts=parts,
            threshold=thr,
            engine="dashboard",
        )
        if not pt:
            return False
        x, y = pt
        self._click(x, y, hover_delay_s=0.20, post_delay_s=0.20)
        return True

    # --- verification -----------------------------------------------------

    def _token_present_in_buffs_zone(self, token: str, parts: List[str], thr: float) -> bool:
        """
        Проверка наличия ОДНОГО токена в зоне current_buffs.
        Используем match_multi_in_zone с map из одного ключа, чтобы получить мульти-масштаб (как в respawn).
        """
        win = self._win()
        if not win:
            return False
        ltrb = self._zone_ltrb(win, "current_buffs")
        res = match_multi_in_zone(
            window=win,
            zone_ltrb=ltrb,
            server=self.server,
            lang=self._lang(),
            templates_map={token: parts},
            key_order=[token],
            threshold=thr,
            engine="dashboard",
            scales=(1.0, 0.9, 1.1),
            debug=False,
        )
        return res is not None

    def verify_selected_buffs(self, tokens: List[str], thr: float = 0.86) -> bool:
        """
        True, если КАЖДЫЙ токен из tokens виден в зоне current_buffs.
        (мульти-масштабный матч отдельно для каждого токена)
        """
        win = self._win()
        if not win:
            return False
        if not tokens:
            return True

        # Собираем map token->parts из BUFFS/DANCES/SONGS
        icons: Dict[str, List[str]] = {}
        all_maps = (BUFFS or {}) | (DANCES or {}) | (SONGS or {})
        for t in tokens:
            parts = all_maps.get(t)
            if parts:
                icons[t] = parts

        if len(icons) != len(tokens):
            return False

        for tok, parts in icons.items():
            if not self._token_present_in_buffs_zone(tok, parts, thr):
                return False
        return True
