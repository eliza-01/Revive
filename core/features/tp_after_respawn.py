# core/features/tp_after_respawn.py
from __future__ import annotations
import time
from typing import Callable, Optional, Dict

from core.features.flow_actions import FlowActions

TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"

class TPAfterDeathWorker:
    def __init__(self, controller, window_info: Optional[dict], get_language: Callable[[], str],
                 on_status: Callable[[str, Optional[bool]], None] = lambda *_: None,
                 check_is_dead: Optional[Callable[[], bool]] = None, wait_alive_timeout_s: float = 1.0):
        self._actions = FlowActions(controller, "l2mad", lambda: window_info, get_language, on_status)
        self._category_id: Optional[str] = None
        self._location_id: Optional[str] = None
        self._method = TP_METHOD_DASHBOARD
        self._check_is_dead = check_is_dead
        self._wait_alive_timeout_s = float(wait_alive_timeout_s)

    def configure(self, category_id: str, location_id: str, method: str = TP_METHOD_DASHBOARD):
        self._category_id = category_id; self._location_id = location_id; self._method = (method or TP_METHOD_DASHBOARD).lower()

    def set_method(self, method: str): self._method = (method or TP_METHOD_DASHBOARD).lower()
    def start(self): pass
    def stop(self): pass

    def _wait_until_alive(self, timeout_s: float) -> bool:
        if not callable(self._check_is_dead): return True
        deadline = time.time() + float(timeout_s)
        while time.time() < deadline:
            try:
                if not self._check_is_dead(): return True
            except Exception:
                return True
            time.sleep(5)
        return False

    def teleport_now(self, category_id: str, location_id: str, method: Optional[str] = None) -> bool:
        if method: self._method = (method or TP_METHOD_DASHBOARD).lower()
        self._category_id = category_id; self._location_id = location_id
        if not self._wait_until_alive(timeout_s=self._wait_alive_timeout_s): return False
        if self._method == TP_METHOD_DASHBOARD:
            return self._actions.tp_dashboard(self._category_id, self._location_id)
        return False  # gatekeeper пока не реализован
