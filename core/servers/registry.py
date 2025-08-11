# core/servers/registry.py
# РЕЕСТР СЕРВЕРОВ: каждый сервер описывается в core.servers.<server_id>.profile
# Профиль сервера определяет поддерживаемые методы ТП и бафа.
import importlib
from typing import List, Protocol

TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"

BUFF_METHOD_DASHBOARD = "dashboard"
BUFF_METHOD_NPC = "npc"

class ServerProfileProto(Protocol):
    id: str
    name: str
    def tp_supported_methods(self) -> List[str]: ...
    def buff_supported_methods(self) -> List[str]: ...
    def supports_buffing(self) -> bool: ...
    def set_buff_mode(self, mode: str) -> None: ...
    def get_buff_mode(self) -> str: ...

def get_server_profile(server_id: str) -> ServerProfileProto:
    """
    Загружает профиль: core.servers.<server_id>.profile:ServerProfile
    """
    module_name = f"core.servers.{server_id}.profile"
    mod = importlib.import_module(module_name)
    return getattr(mod, "ServerProfile")()

def list_servers() -> List[str]:
    """
    Верни список известных серверов.
    По-хорошему — собрать динамически. Пока — статично.
    """
    return ["l2mad", "ketrawars", "euro-pvp"]
