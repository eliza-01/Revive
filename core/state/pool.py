from __future__ import annotations
from typing import Any, Dict, Iterable
import time

def ensure_pool(s: Dict[str, Any]) -> Dict[str, Any]:
    if "_state" not in s:
        s["_state"] = {}
    st = s["_state"]
    st.setdefault("window",  {"info": None, "found": False, "ts": 0.0})
    st.setdefault("focus",   {"has_focus": None, "ts": 0.0})
    st.setdefault("player",  {"alive": None, "hp_ratio": None, "cp_ratio": None, "ts": 0.0})
    st.setdefault("features",{
        "respawn": {
            "enabled": False,
            "wait_enabled": False,      # ← добавить
            "wait_seconds": 120,        # ← добавить
            "status": "idle",
            "ts": 0.0
        },
        "buff":     {"enabled": False, "status": "idle", "ts": 0.0, "mode": ""},
        "macros":   {"enabled": False, "repeat_enabled": False, "rows": [], "status": "idle", "ts": 0.0},
        "tp":       {"enabled": False, "status": "idle", "ts": 0.0},
        "autofarm": {"enabled": False, "status": "idle", "ts": 0.0},
    })
    st.setdefault("pipeline", {"allowed": ["respawn","buff","macros","tp","autofarm"],
                               "order": ["respawn","macros"],
                               "active": False, "idx": 0, "last_step": "", "ts": 0.0})
    st.setdefault("services", {"player_state": {"running": False},
                               "window_focus": {"running": False},
                               "macros_repeat": {"running": False}})
    return st

def _walk(d: Dict[str, Any], path: Iterable[str]) -> Dict[str, Any]:
    cur = d
    for p in path[:-1]:
        cur = cur.setdefault(p, {})
    return cur

def pool_set(s: Dict[str, Any], path: str, value: Any) -> None:
    st = ensure_pool(s)
    parts = [p for p in path.split(".") if p]
    if not parts: return
    parent = _walk(st, parts)
    parent[parts[-1]] = value

def pool_merge(s: Dict[str, Any], path: str, mapping: Dict[str, Any], add_ts: bool = True) -> None:
    st = ensure_pool(s)
    parts = [p for p in path.split(".") if p]
    if not parts: return
    parent = _walk(st, parts)
    node = parent.setdefault(parts[-1], {})
    if add_ts and "ts" not in mapping:
        mapping = dict(mapping)
        mapping["ts"] = time.time()
    node.update(mapping)

def pool_get(s: Dict[str, Any], path: str, default: Any = None) -> Any:
    st = ensure_pool(s)
    cur: Any = st
    for p in [p for p in path.split(".") if p]:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur
