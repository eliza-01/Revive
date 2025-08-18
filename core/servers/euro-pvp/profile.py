# core/servers/euro-pvp/profile.py
# Пример профиля сервера с ТОЛЬКО gatekeeper-ТП и бафом через NPC.
from typing import List
from core.servers.registry import (
    TP_METHOD_GATEKEEPER,
    BUFF_METHOD_NPC,
)

class ServerProfile:
    id = "gk_only"
    name = "GKOnly"

    def __init__(self):
        self._buff_mode = "profile"

    def tp_supported_methods(self) -> List[str]:
        return [TP_METHOD_GATEKEEPER]

    def buff_supported_methods(self) -> List[str]:
        return [BUFF_METHOD_NPC]

    def supports_buffing(self) -> bool:
        return True

    def set_buff_mode(self, mode: str):
        self._buff_mode = (mode or "profile").lower()

    def get_buff_mode(self) -> str:
        return self._buff_mode
