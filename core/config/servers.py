# core/config/servers.py
from __future__ import annotations
import json
import os
from typing import Dict, List, Any
from core.logging import console

# Путь к манифесту рядом с этим файлом
_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "servers.manifest.json")
_manifest_cache: Dict[str, Any] | None = None


def _ve(msg: str):
    """Локальный helper: шлём текст в консоль и выбрасываем ValueError (без фолбэков)."""
    console.log(f"[manifest] {msg}")
    raise ValueError(msg)


def _load_manifest() -> Dict[str, Any]:
    """Читает и кэширует servers.manifest.json без фолбэков."""
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
        _manifest_cache = json.load(f)
    return _manifest_cache


def _current_assembly_blob() -> Dict[str, Any]:
    m = _load_manifest()
    cur = m.get("current_assembly")
    assemblies = m.get("assemblies") or {}
    if not cur or cur not in assemblies:
        _ve("Invalid servers.manifest.json: current_assembly not found")
    return assemblies[cur]


def _servers_dict() -> Dict[str, Dict[str, Any]]:
    asm = _current_assembly_blob()
    servers = asm.get("servers")
    if not isinstance(servers, dict):
        _ve("Invalid servers.manifest.json: 'servers' must be an object")
    return servers


def _server(server_id: str) -> Dict[str, Any]:
    servers = _servers_dict()
    if server_id not in servers:
        _ve(f"Unknown server id: {server_id}")
    return servers[server_id]


# -------------------- Публичный API для приложения --------------------

def list_servers() -> List[str]:
    """Список ID серверов из текущего assembly (порядок — как в манифесте)."""
    return list(_servers_dict().keys())


def get_languages(server_id: str) -> List[str]:
    """Доступные языки интерфейса L2 для сервера (system.languages)."""
    sys = (_server(server_id).get("system") or {})
    langs = sys.get("languages") or []
    if not isinstance(langs, list):
        _ve(f"Invalid languages for server '{server_id}'")
    return list(langs)


def get_section_flags(server_id: str) -> Dict[str, bool]:
    """
    Видимость секций по серверу: { section_id: bool }.
    Берём флаг 'section' из соответствующих разделов в манифесте.
    """
    data = _server(server_id)
    out: Dict[str, bool] = {}
    for k, v in data.items():
        if isinstance(v, dict) and "section" in v:
            out[k] = bool(v["section"])
    return out


def get_buff_methods(server_id: str) -> List[str]:
    """Список методов бафа (buff.methods)."""
    buff = (_server(server_id).get("buff") or {})
    methods = buff.get("methods") or []
    if not isinstance(methods, list):
        _ve(f"Invalid buff.methods for server '{server_id}'")
    return list(methods)


def get_buff_modes(server_id: str) -> List[str]:
    """Список режимов бафа (buff.modes)."""
    buff = (_server(server_id).get("buff") or {})
    modes = buff.get("modes") or []
    if not isinstance(modes, list):
        _ve(f"Invalid buff.modes for server '{server_id}'")
    return list(modes)

def get_autofarm_modes(server_id: str) -> List[str]:
    """Список режимов автофарма (autofarm.modes)."""
    af = (_server(server_id).get("autofarm") or {})
    modes = af.get("modes") or []
    if not isinstance(modes, list):
        _ve(f"Invalid autofarm.modes for server '{server_id}'")
    return list(modes)

# -------- Teleport --------

def get_teleport_methods(server_id: str) -> List[str]:
    """Список методов ТП (teleport.methods)."""
    tp = (_server(server_id).get("teleport") or {})
    methods = tp.get("methods") or []
    if not isinstance(methods, list):
        _ve(f"Invalid teleport.methods for server '{server_id}'")
    return list(methods)


def get_teleport_categories(server_id: str) -> List[str]:
    """
    Категории ТП из манифеста.
    Поддерживаем новый формат:
      "categories": { "<category>": { "locations": [...] }, ... }
    и легаси (списком), если вдруг встретится.
    """
    tp = (_server(server_id).get("teleport") or {})
    cats = tp.get("categories") or {}
    if isinstance(cats, dict):
        # порядок сохранится как в JSON
        return list(cats.keys())
    if isinstance(cats, list):  # легаси
        return list(cats)
    _ve(f"Invalid teleport.categories for server '{server_id}'")
    return []  # недостижимо


def get_teleport_locations(server_id: str, category: str) -> List[str]:
    """
    Локации для категории (новый формат манифеста).
    Если категория не найдена, вернём [].
    Для легаси манифеста вернём плоский 'locations' (без учёта категории).
    """
    tp = (_server(server_id).get("teleport") or {})
    cats = tp.get("categories") or {}
    if isinstance(cats, dict):
        entry = cats.get(str(category) if category is not None else "") or {}
        locs = entry.get("locations") or []
        if not isinstance(locs, list):
            _ve(f"Invalid teleport.categories[{category}].locations for server '{server_id}'")
        return [str(x) for x in locs]
    # легаси
    locs = tp.get("locations") or []
    if isinstance(locs, list):
        return [str(x) for x in locs]
    _ve(f"Invalid legacy teleport.locations for server '{server_id}'")
    return []
