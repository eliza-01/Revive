# core/features/buff_after_respawn.py
from __future__ import annotations
from typing import Callable, Optional, Dict

from core.features.flow_actions import FlowActions

BUFF_MODE_PROFILE = "profile"
BUFF_MODE_MAGE = "mage"
BUFF_MODE_FIGHTER = "fighter"

class BuffAfterRespawnWorker:
    def __init__(self, controller, server: str, get_window: Callable[[], Optional[Dict]], get_language: Callable[[], str],
                 on_status: Callable[[str, Optional[bool]], None] = lambda *_: None, click_threshold: float = 0.87, debug: bool = False):
        self._mode = BUFF_MODE_PROFILE
        self._actions = FlowActions(controller, server, get_window, get_language, on_status)

    def set_mode(self, mode: str):
        m = (mode or BUFF_MODE_PROFILE).lower()
        self._mode = m if m in (BUFF_MODE_PROFILE, BUFF_MODE_MAGE, BUFF_MODE_FIGHTER) else BUFF_MODE_PROFILE

    def set_method(self, _method: str): pass

    def _mode_tpl_key(self) -> str:
        return {
            BUFF_MODE_PROFILE: "buffer_mode_profile",
            BUFF_MODE_MAGE: "buffer_mode_mage",
            BUFF_MODE_FIGHTER: "buffer_mode_fighter",
        }[self._mode]

    def run_once(self) -> bool:
        return self._actions.buff(self._mode_tpl_key)
