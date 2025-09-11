from __future__ import annotations
from typing import Any, Dict, Iterable
import time


def ensure_pool(state: Dict[str, Any]) -> Dict[str, Any]:
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

    # ---- Окно/фокус/игрок/ui_guard ----
    st.setdefault("window", {"info": None, "found": False, "title": "", "ts": 0.0})
    st.setdefault("focus", {"is_focused": None, "ts": 0.0})
    st.setdefault("player", {"alive": None, "hp_ratio": None, "cp_ratio": None, "ts": 0.0})
    st.setdefault("ui_guard", {"enabled": False, "tracker": "empty", "ts": 0.0})

    # ---- Фичи ----
    st.setdefault("features", {
        "respawn": {
            "enabled": False, "wait_enabled": False, "wait_seconds": 120,
            "click_threshold": 0.70, "confirm_timeout_s": 6.0,
            "status": "idle", "busy": False, "waiting": False, "ts": 0.0,
        },
        "buff": {
            "enabled": False, "mode": "", "methods": [],
            "status": "idle", "busy": False, "waiting": False, "ts": 0.0,
        },
        "macros": {
            "enabled": False, "repeat_enabled": False, "rows": [],
            "status": "idle", "busy": False, "waiting": False, "ts": 0.0,
        },
        "tp": {
            "enabled": False, "method": "dashboard", "category": "", "location": "", "row_id": "",
            "status": "idle", "busy": False, "waiting": False, "ts": 0.0,
        },
        "autofarm": {
          "enabled": False,
          "mode": "manual",           # "auto" | "manual"
          "status": "idle", "busy": False, "waiting": False,
          "config": {
            "profession": "",
            "skills": [{"key":"1","slug":"", "cast_ms":1100}],
            "zone": "",
            "monsters": []
          },
          "ts": 0.0
        }
    })

    # ---- Пайплайн ----
    st.setdefault("pipeline", {
        "allowed": ["respawn", "buff", "macros", "tp", "autofarm"],
        "order": ["respawn", "macros", "autofarm"],
        "active": False, "idx": 0, "last_step": "", "ts": 0.0,
    })

    # ---- Сервисы ----
    st.setdefault("services", {
        "player_state": {"running": False, "ts": 0.0},
        "window_focus": {"running": False, "ts": 0.0},
        "macros_repeat": {"running": False, "ts": 0.0},
        "autofarm": {"running": False, "ts": 0.0},
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


# ── JSON-safe дамп всего state ───────────────────────────────────────────────
def _round_numbers(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, 3)
    if isinstance(v, dict):
        return {k: _round_numbers(v2) for k, v2 in v.items()}
    if isinstance(v, list):
        return [_round_numbers(x) for x in v]
    if isinstance(v, tuple):
        return tuple(_round_numbers(x) for x in v)
    return v

def _json_sanitize(x: Any) -> Any:
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if isinstance(x, dict):
        return {k: _json_sanitize(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_sanitize(v) for v in x]
    return f"<{x.__class__.__name__}>"

def dump_pool(state: Dict[str, Any], *, compact: bool = True) -> Dict[str, Any]:
    """
    Возвращает JSON-безопасную копию текущего state (единый пул в корне).
    compact=True слегка округляет float'ы.
    """
    ensure_pool(state)
    data = state
    return _json_sanitize(_round_numbers(data) if compact else data)
