# core/config/servers.py
from __future__ import annotations
from typing import List

BUFF_METHOD_DASHBOARD = "dashboard"
BUFF_METHOD_NPC = "npc"
TP_METHOD_DASHBOARD = "dashboard"


class ServerProfile:
    __slots__ = ("id", "name", "_buff_mode")

    def __init__(self, server_id: str):
        self.id = server_id
        self.name = server_id
        self._buff_mode = BUFF_METHOD_DASHBOARD

    def tp_supported_methods(self) -> List[str]:
        return [TP_METHOD_DASHBOARD]

    def buff_supported_methods(self) -> List[str]:
        # return [BUFF_METHOD_DASHBOARD, BUFF_METHOD_NPC]
        return [BUFF_METHOD_DASHBOARD]

    def supports_buffing(self) -> bool:
        return True

    def set_buff_mode(self, mode: str) -> None:
        if mode not in self.buff_supported_methods():
            raise ValueError(f"Unsupported buff mode: {mode}")
        self._buff_mode = mode

    def get_buff_mode(self) -> str:
        return self._buff_mode


_REGISTRY: List[str] = ["boh", "l2mad"]


def list_servers() -> List[str]:
    return list(_REGISTRY)


def get_server_profile(server_id: str) -> ServerProfile:
    if server_id not in _REGISTRY:
        raise ValueError(f"Unknown server id: {server_id}")
    return ServerProfile(server_id)
