# core/state/pool.py
from __future__ import annotations
from typing import Any, Dict, Iterable
import time


def ensure_pool(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    ЕДИНЫЙ пул состояния живёт прямо в корневом dict `state`.
    Никаких sys_st. и state["_state"] больше нет.
    """
    st = state

    # ---- Конфиг/мета ----
    st.setdefault("app", {
        "version": "",
        "update": {"available": False, "remote": "", "ts": 0.0},
        "ts": 0.0,
    })
    st.setdefault("config", {
        "server": "boh",
        "language": "rus",
        "profile": {},
        "profiles": [],
        "ts": 0.0,
    })
    st.setdefault("account", {"login": "", "password": "", "pin": "", "ts": 0.0})

    # ---- Окно/фокус/игрок ----
    st.setdefault("window", {"info": None, "found": False, "title": "", "ts": 0.0})
    st.setdefault("focus", {"has_focus": None, "ts": 0.0})
    st.setdefault("player", {"alive": None, "hp_ratio": None, "cp_ratio": None, "ts": 0.0})

    # ---- Фичи ----
    st.setdefault("features", {
        "respawn": {
            "enabled": False, "wait_enabled": False, "wait_seconds": 120,
            "click_threshold": 0.70, "confirm_timeout_s": 6.0,
            "status": "idle", "ts": 0.0,
        },
        "buff": {
            "enabled": False, "mode": "", "methods": [],
            "status": "idle", "ts": 0.0,
        },
        "macros": {
            "enabled": False, "repeat_enabled": False, "rows": [],
            # опционально простые поля
            "run_always": False, "delay_s": 1.0, "duration_s": 2.0, "sequence": ["1"],
            "status": "idle", "ts": 0.0,
        },
        "tp": {
            "enabled": False, "method": "dashboard", "category": "", "location": "", "row_id": "",
            "status": "idle", "ts": 0.0,
        },
        "autofarm": {"enabled": False, "status": "idle", "ts": 0.0},
    })

    # ---- Пайплайн ----
    st.setdefault("pipeline", {
        "allowed": ["respawn", "buff", "macros", "tp", "autofarm"],
        "order": ["respawn", "macros"],
        "active": False, "idx": 0, "last_step": "", "ts": 0.0,
    })

    # ---- Сервисы ----
    st.setdefault("services", {
        "player_state": {"running": False, "ts": 0.0},
        "window_focus": {"running": False, "ts": 0.0},
        "macros_repeat": {"running": False, "ts": 0.0},
    })

    # ---- UI-статусы ----
    ui = st.setdefault("ui_status", {})
    for scope in ("driver", "window", "watcher", "update", "buff", "macros", "tp", "respawn", "focus"):
        ui.setdefault(scope, {"text": "", "ok": None, "ts": 0.0})

    # ---- Runtime/Debug ----
    st.setdefault("runtime", {
        "orch": {"busy_until": 0.0, "active": False, "ts": 0.0},
        "debug": {
            "respawn_debug": False, "pipeline_debug": False, "pool_debug": False, "ts": 0.0,
        }
    })
    return st


def _walk(d: Dict[str, Any], path: Iterable[str]) -> Dict[str, Any]:
    cur = d
    for p in path[:-1]:
        cur = cur.setdefault(p, {})
    return cur


def pool_set(state: Dict[str, Any], path: str, value: Any) -> None:
    st = ensure_pool(state)
    parts = [p for p in path.split(".") if p]
    if not parts:
        return
    parent = _walk(st, parts)
    parent[parts[-1]] = value


def pool_merge(state: Dict[str, Any], path: str, mapping: Dict[str, Any], add_ts: bool = True) -> None:
    st = ensure_pool(state)
    parts = [p for p in path.split(".") if p]
    if not parts:
        return
    parent = _walk(st, parts)
    node = parent.setdefault(parts[-1], {})
    if add_ts and "ts" not in mapping:
        mapping = dict(mapping)
        mapping["ts"] = time.time()
    node.update(mapping)


def pool_write(state: Dict[str, Any], path: str, mapping: Dict[str, Any], *, add_ts: bool = True) -> None:
    pool_merge(state, path, mapping, add_ts=add_ts)


def pool_get(state: Dict[str, Any], path: str, default: Any = None) -> Any:
    st = ensure_pool(state)
    cur: Any = st
    for p in [p for p in path.split(".") if p]:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur
