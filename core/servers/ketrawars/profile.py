# core/servers/ketrawars/profile.py
# Пример профиля сервера с ТОЛЬКО dashboard-ТП и dashboard-бафом.
from typing import List
from core.servers.registry import (
    TP_METHOD_DASHBOARD,
    BUFF_METHOD_DASHBOARD,
)

class ServerProfile:
    id = "dash_only"
    name = "DashOnly"

    def __init__(self):
        self._buff_mode = "profile"

    def tp_supported_methods(self) -> List[str]:
        return [TP_METHOD_DASHBOARD]

    def buff_supported_methods(self) -> List[str]:
        return [BUFF_METHOD_DASHBOARD]

    def supports_buffing(self) -> bool:
        return True

    def set_buff_mode(self, mode: str):
        self._buff_mode = (mode or "profile").lower()

    def get_buff_mode(self) -> str:
        return self._buff_mode
