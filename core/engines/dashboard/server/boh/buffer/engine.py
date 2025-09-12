# core/engines/dashboard/server/boh/buffer/engine.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

from core.logging import console
from core.state.pool import pool_get
from ..engine import _match_on_window, _visible, _click_center
from ..dashboard_data import TEMPLATES

class BufferEngine:
    """
    Низкоуровневые операции вкладки Buffer:
      - клик по плитке режима (profile/fighter/mage/archer)
      - (позже) проверка, что баф применён
    Предполагается, что Dashboard уже открыт и активна вкладка Buffer.
    """
    def __init__(self, state: Dict[str, Any], server: str, controller: Any, get_window, get_language):
        self.s = state
        self.server = (server or "boh").lower()
        self.controller = controller
        self.get_window = get_window
        self.get_language = get_language

    def _hud(self, status: str, text: str):
        try:
            console.hud(status, text)
        except Exception:
            console.log(f"[HUD/{status}] {text}")

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

    def is_open(self, thr: float = 0.87) -> bool:
        win = self._win()
        if not win:
            return False
        return _visible(win, self._lang(), "dashboard_buffer_init", "fullscreen", thr)

    def click_mode(self, mode: Optional[str] = None, thr: float = 0.87) -> bool:
        """
        Клик по плитке режима. Если нет точного — пробуем profile как фолбэк.
        """
        win = self._win()
        if not win:
            self._hud("err", "[dashboard/buffer] окно игры не найдено")
            return False

        if not mode:
            mode = pool_get(self.s, "features.buff.mode", "") or "profile"
        mode = str(mode).strip().lower()

        cand = [f"dashboard_buffer_{mode}"]
        if mode != "profile":
            cand.append("dashboard_buffer_profile")

        lang = self._lang()
        for key in cand:
            if key not in TEMPLATES:
                continue
            rect = _match_on_window(win, lang, key, "fullscreen", thr)
            if rect:
                _click_center(self.controller, rect)
                self._hud("succ", "[dashboard] Бафаемся")
                return True

        self._hud("err", f"[dashboard/buffer] плитка '{mode}' не найдена")
        return False

    # Заглушка — сюда добавим детекцию «баф применён»
    def verify_buff_applied(self) -> bool:
        return True
