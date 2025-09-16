# core/orchestrators/snapshot.py
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time

from core.state.pool import pool_get
from core.logging import console  # можно убрать, если не нужен

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

    # --- focus --- (диагностика)
    is_focused = pool_get(state, "focus.is_focused", None)
    focus_ts = float(pool_get(state, "focus.ts", 0.0) or 0.0)
    unfocused_for = (
        max(0.0, time.time() - focus_ts)
        if (is_focused is False and focus_ts > 0.0)
        else None
    )

    # --- features flags ---
    respawn_enabled = bool(pool_get(state, "features.respawn.enabled", False))
    macros_enabled  = bool(pool_get(state, "features.macros.enabled",  False))
    buff_enabled    = bool(pool_get(state, "features.buff.enabled",    False))
    teleport_enabled= bool(pool_get(state, "features.teleport.enabled",False))
    autofarm_enabled= bool(pool_get(state, "features.autofarm.enabled",False))

    # --- extras: сигналы пауз/состояний ---
    ui_guard_busy   = bool(pool_get(state, "features.ui_guard.busy",   False))
    ui_guard_paused = bool(pool_get(state, "features.ui_guard.paused", False))
    ui_guard_report = str(pool_get(state, "features.ui_guard.report", "empty") or "empty")

    # отдельные хелперы
    def _feat_paused(name: str) -> bool:
        return bool(pool_get(state, f"features.{name}.paused", False))

    def _svc_paused(name: str) -> bool:
        return bool(pool_get(state, f"services.{name}.paused", False))

    # наборы для агрегатов
    feature_keys = ["respawn", "buff", "teleport", "macros", "record", "autofarm", "ui_guard", "stabilize"]
    service_keys = ["player_state", "macros_repeat", "autofarm"]

    any_feature_paused_only  = any(_feat_paused(k) for k in feature_keys)
    any_service_paused       = any(_svc_paused(k) for k in service_keys)

    # состояние самого пайплайна (для удобства правил)
    pipeline_paused        = bool(pool_get(state, "pipeline.paused", False))
    pipeline_pause_reason  = str(pool_get(state, "pipeline.pause_reason", "") or "")

    # объединённый флаг (как используется в Pipeline.when)
    any_feature_or_service_paused = (
        any_feature_paused_only or any_service_paused or ui_guard_paused or pipeline_paused
    )

    extras = {
        # ui-guard
        "ui_guard_busy": ui_guard_busy,
        "ui_guard_paused": ui_guard_paused,
        "ui_guard_report": ui_guard_report,

        # паузы по подсистемам
        "any_feature_paused_only": any_feature_paused_only,   # только фичи
        "any_service_paused": any_service_paused,             # только сервисы
        "any_feature_paused": any_feature_or_service_paused,  # ОБЪЕДИНЁННЫЙ (то, что вы читаете в пайплайне)

        # статус пайплайна (удобно иметь под рукой)
        "pipeline_paused": pipeline_paused,
        "pipeline_pause_reason": pipeline_pause_reason,
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
