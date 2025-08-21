from __future__ import annotations
from typing import List
from core.servers.registry import (
    BUFF_METHOD_DASHBOARD, BUFF_METHOD_NPC,
    TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER,
)

class ServerProfile:
    id = "boh"
    name = "BOH"

    def __init__(self):
        self._buff_mode = BUFF_METHOD_DASHBOARD

    def tp_supported_methods(self) -> List[str]:
        return [TP_METHOD_DASHBOARD]

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
