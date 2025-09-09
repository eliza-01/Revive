# core/orchestrators/snapshot.py
from dataclasses import dataclass, field
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

    # единообразные флаги фич
    respawn_enabled: bool
    buff_enabled: bool
    tp_enabled: bool
    macros_enabled: bool
    autofarm_enabled: bool

    extras: Dict[str, Any] = field(default_factory=dict)


def build_snapshot(state: Dict[str, Any], _ps_adapter=None) -> Snapshot:
    """
    Единый builder снапшота ИСКЛЮЧИТЕЛЬНО из пула (_state).
    Параметр _ps_adapter оставлен для совместимости сигнатуры, но не используется.
    """
    # --- window ---
    win_info = pool_get(state, "window.info", None)
    win_found = bool(pool_get(state, "window.found", False))
    has_window = bool(
        win_found
        and isinstance(win_info, dict)
        and "width" in win_info
        and "height" in win_info
    )

    # --- player ---
    alive = pool_get(state, "player.alive", None)
    hp_ratio = pool_get(state, "player.hp_ratio", None)
    try:
        hp_ratio = float(hp_ratio) if hp_ratio is not None else None
    except Exception:
        hp_ratio = None

    # --- focus ---
    has_focus = pool_get(state, "focus.has_focus", None)
    focus_ts = float(pool_get(state, "focus.ts", 0.0) or 0.0)
    unfocused_for = (
        max(0.0, time.time() - focus_ts)
        if (has_focus is False and focus_ts > 0.0)
        else None
    )

    # --- features flags (только из пула) ---
    respawn_enabled = bool(pool_get(state, "features.respawn.enabled", False))
    macros_enabled = bool(pool_get(state, "features.macros.enabled", False))
    buff_enabled = bool(pool_get(state, "features.buff.enabled", False))
    tp_enabled = bool(pool_get(state, "features.tp.enabled", False))
    autofarm_enabled = bool(pool_get(state, "features.autofarm.enabled", False))

    return Snapshot(
        has_window=has_window,
        has_focus=has_focus,
        alive=alive,
        hp_ratio=hp_ratio,
        focus_unfocused_for_s=unfocused_for,
        respawn_enabled=respawn_enabled,
        buff_enabled=buff_enabled,
        tp_enabled=tp_enabled,
        macros_enabled=macros_enabled,
        autofarm_enabled=autofarm_enabled,
    )
