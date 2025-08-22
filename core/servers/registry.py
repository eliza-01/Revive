# РЕЕСТР СЕРВЕРОВ: автопоиск core.servers.<server_id> c profile.py
from __future__ import annotations
from importlib import import_module
import pkgutil
from typing import List, Protocol, Optional

import core.servers as _servers_pkg

# --- публичные константы (как раньше) ---
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


def _has_profile_pkg(server: str) -> bool:
    """Есть ли core.servers.<server>.profile и экспорт ServerProfile/PROFILE."""
    try:
        mod = import_module(f"core.servers.{server}.profile")
    except Exception:
        return False
    return hasattr(mod, "ServerProfile") or hasattr(mod, "PROFILE")


def list_servers(require_profile: bool = True) -> List[str]:
    """
    Сканирует core.servers и возвращает список подпакетов (серверов).
    Если require_profile=True — оставляет только те, где есть profile.py.
    """
    servers: List[str] = []
    for m in pkgutil.iter_modules(_servers_pkg.__path__):
        if not m.ispkg:
            continue
        name = m.name
        if name.startswith("_"):
            continue
        if require_profile and not _has_profile_pkg(name):
            continue
        servers.append(name)
    servers.sort()
    return servers


def get_server_profile(server_id: str) -> ServerProfileProto:
    """
    Загружает core.servers.<server_id>.profile и возвращает экземпляр профиля.
    Поддерживает оба варианта:
      - class ServerProfile: ...  -> вернёт ServerProfile()
      - PROFILE = <obj>          -> вернёт PROFILE
    """
    mod = import_module(f"core.servers.{server_id}.profile")
    if hasattr(mod, "ServerProfile"):
        return getattr(mod, "ServerProfile")()  # type: ignore[no-any-return]
    if hasattr(mod, "PROFILE"):
        return getattr(mod, "PROFILE")         # type: ignore[no-any-return]
    raise ImportError(f"Profile for server '{server_id}' not found (no ServerProfile/PROFILE).")
