# core/orchestrators/snapshot.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class Snapshot:
    """Единый снимок состояния для оркестратора."""
    has_window: bool
    alive: Optional[bool]         # True=жив, False=мертв, None=неизвестно
    hp_ratio: Optional[float]     # 0.0–1.0 или None
    respawn_enabled: bool
    autofarm_enabled: bool
    # можно добавлять новые поля (tp_enabled, buff_enabled и т.д.)

    extras: Dict[str, Any] = None   # для расширений


def build_snapshot(sys_state: Dict[str, Any], watcher) -> Snapshot:
    """
    Собираем срез состояния на основе sys_state и watcher.
    Делается в начале каждого тика оркестратора.
    """
    win = sys_state.get("window")
    has_window = bool(win and win.get("width") and win.get("height"))

    try:
        alive = watcher.is_alive()
    except Exception:
        alive = None

    try:
        st = watcher.last()
        hp_ratio = float(getattr(st, "hp_ratio", 0.0))
    except Exception:
        hp_ratio = None

    return Snapshot(
        has_window=has_window,
        alive=alive,
        hp_ratio=hp_ratio,
        respawn_enabled=bool(sys_state.get("respawn_enabled")),
        autofarm_enabled=bool(sys_state.get("af_enabled")),
        extras={}
    )
