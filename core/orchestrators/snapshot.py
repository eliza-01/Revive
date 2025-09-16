# core/orchestrators/snapshot.py
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time

from core.state.pool import pool_get
from core.logging import console

@dataclass
class Snapshot:
    has_window: bool
    alive: Optional[bool]
    hp_ratio: Optional[float]
    is_focused: Optional[bool]
    focus_unfocused_for_s: Optional[float]

    # единообразные флаги фич
    respawn_enabled: bool
    buff_enabled: bool
    teleport_enabled: bool
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
        win_found and isinstance(win_info, dict) and "width" in win_info and "height" in win_info
    )

    # --- player ---
    alive = pool_get(state, "player.alive", None)
    hp_ratio = pool_get(state, "player.hp_ratio", None)
    try:
        hp_ratio = float(hp_ratio) if hp_ratio is not None else None
    except Exception:
        hp_ratio = None

    # --- focus --- (оставляем как диагностический сигнал) ---
    is_focused = pool_get(state, "focus.is_focused", None)
    focus_ts = float(pool_get(state, "focus.ts", 0.0) or 0.0)
    unfocused_for = (max(0.0, time.time() - focus_ts)
                     if (is_focused is False and focus_ts > 0.0) else None)

    # --- features flags ---
    respawn_enabled = bool(pool_get(state, "features.respawn.enabled", False))
    macros_enabled = bool(pool_get(state, "features.macros.enabled", False))
    buff_enabled = bool(pool_get(state, "features.buff.enabled", False))
    teleport_enabled = bool(pool_get(state, "features.teleport.enabled", False))
    autofarm_enabled = bool(pool_get(state, "features.autofarm.enabled", False))

    # --- extras: сигналы пауз ---
    ui_guard_busy = bool(pool_get(state, "features.ui_guard.busy", False))
    ui_guard_paused = bool(pool_get(state, "features.ui_guard.paused", False))
    ui_guard_report = str(pool_get(state, "features.ui_guard.report", "empty") or "empty")

    def _feat_paused(name: str) -> bool:
        return bool(pool_get(state, f"features.{name}.paused", False))

    def _svc_paused(name: str) -> bool:
        return bool(pool_get(state, f"services.{name}.paused", False))

    any_feature_paused = any([
        _feat_paused("respawn"),
        _feat_paused("buff"),
        _feat_paused("teleport"),
        _feat_paused("macros"),
        _feat_paused("record"),
        _feat_paused("autofarm"),
        _svc_paused("player_state"),
        _svc_paused("macros_repeat"),
        _svc_paused("autofarm"),
        ui_guard_paused,
    ])

    extras = {
        "ui_guard_busy": ui_guard_busy,
        "ui_guard_paused": ui_guard_paused,
        "ui_guard_report": ui_guard_report,
        "any_feature_paused": any_feature_paused,
    }

    return Snapshot(
        has_window=has_window,
        is_focused=is_focused,
        alive=alive,
        hp_ratio=hp_ratio,
        focus_unfocused_for_s=unfocused_for,
        respawn_enabled=respawn_enabled,
        buff_enabled=buff_enabled,
        teleport_enabled=teleport_enabled,
        macros_enabled=macros_enabled,
        autofarm_enabled=autofarm_enabled,
        extras=extras,
    )
