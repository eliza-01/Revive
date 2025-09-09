# core/orchestrators/snapshot.py

from dataclasses import dataclass
from typing import Any, Dict, Optional
import time
from core.state.pool import pool_get

@dataclass
class Snapshot:
    has_window: bool
    alive: Optional[bool]
    hp_ratio: Optional[float]
    has_focus: Optional[bool]
    focus_unfocused_for_s: Optional[float]

    # ← единообразные флаги фич
    respawn_enabled: bool
    buff_enabled: bool
    tp_enabled: bool
    macros_enabled: bool
    autofarm_enabled: bool

    extras: Dict[str, Any] = None


def build_snapshot(sys_state: Dict[str, Any], _ps_adapter) -> Snapshot:
    win = sys_state.get("window")
    has_window = bool(win and win.get("width") and win.get("height"))

    pool = sys_state.get("_state") or {}
    p = (pool.get("player") or {})
    f = (pool.get("focus") or {})

    alive = p.get("alive")
    try:
        hp_ratio = float(p["hp_ratio"]) if p.get("hp_ratio") is not None else None
    except Exception:
        hp_ratio = None

    has_focus = f.get("has_focus", None)
    ts = float(f.get("ts") or 0.0)
    unfocused_for = max(0.0, time.time() - ts) if (has_focus is False and ts > 0) else None

    # фолбэки к старым полям, если пула нет/пуст
    if alive is None and hp_ratio is None:
        st = _ps_adapter.last() or {}
        alive = st.get("alive", alive)
        try:
            hp_ratio = float(st.get("hp_ratio")) if st.get("hp_ratio") is not None else hp_ratio
        except Exception:
            pass
    if has_focus is None:
        wf_last = sys_state.get("_wf_last") or {}
        has_focus = wf_last.get("has_focus", has_focus)
        ts2 = float(wf_last.get("ts") or 0.0)
        if has_focus is False and ts2 > 0 and unfocused_for is None:
            unfocused_for = max(0.0, time.time() - ts2)

    return Snapshot(
        has_window=has_window,
        has_focus=has_focus,
        alive=alive,
        hp_ratio=hp_ratio,
        focus_unfocused_for_s=unfocused_for,

        # ← читаем единообразно из пула, с фолбэком на старые ключи
        respawn_enabled = bool(pool_get(sys_state, "features.respawn.enabled",  sys_state.get("respawn_enabled"))),
        macros_enabled  = bool(pool_get(sys_state, "features.macros.enabled",   sys_state.get("macros_enabled"))),
        buff_enabled    = bool(pool_get(sys_state, "features.buff.enabled",     sys_state.get("buff_enabled"))),
        tp_enabled      = bool(pool_get(sys_state, "features.tp.enabled",       sys_state.get("tp_enabled"))),
        autofarm_enabled= bool(pool_get(sys_state, "features.autofarm.enabled", sys_state.get("af_enabled"))),

        extras={}
    )