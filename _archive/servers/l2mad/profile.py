# _archive/servers/l2mad/profile.py
from __future__ import annotations
from typing import List
from _archive.servers.registry import (
    BUFF_METHOD_DASHBOARD, BUFF_METHOD_NPC,
    TP_METHOD_DASHBOARD, )

def _server_id() -> str:
    try:
        # 'core.servers.<server_id>'
        return (__package__ or "").split(".")[-1] or "l2mad"
    except Exception:
        return "l2mad"

class ServerProfile:
    id = _server_id()
    name = id

    def __init__(self):
        self._buff_mode = BUFF_METHOD_DASHBOARD  # дефолт

    # --- TP ---
    def tp_supported_methods(self) -> List[str]:
        return [TP_METHOD_DASHBOARD]

    # --- Buff ---
    def buff_supported_methods(self) -> List[str]:
        return [BUFF_METHOD_DASHBOARD, BUFF_METHOD_NPC]

    def supports_buffing(self) -> bool:
        return True

    def set_buff_mode(self, mode: str) -> None:
        if mode not in self.buff_supported_methods():
            raise ValueError(f"Unsupported buff mode: {mode}")
        self._buff_mode = mode

    def get_buff_mode(self) -> str:
        return self._buff_mode
