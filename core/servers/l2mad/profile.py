# core/servers/l2mad/profile.py
# Профиль реального сервера "l2mad": поддерживает оба метода ТП и оба метода бафа.
from typing import List
from core.servers.registry import (
    TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER,
    BUFF_METHOD_DASHBOARD, BUFF_METHOD_NPC,
)

class ServerProfile:
    id = "l2mad"
    name = "L2MAD"

    def __init__(self):
        self._buff_mode = "profile"

    # ------- capabilities -------
    def tp_supported_methods(self) -> List[str]:
        return [TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER]

    def buff_supported_methods(self) -> List[str]:
        return [BUFF_METHOD_DASHBOARD, BUFF_METHOD_NPC]

    def supports_buffing(self) -> bool:
        return True

    # ------- buff mode -------
    def set_buff_mode(self, mode: str):
        self._buff_mode = (mode or "profile").lower()

    def get_buff_mode(self) -> str:
        return self._buff_mode
