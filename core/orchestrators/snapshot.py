# core/orchestrators/snapshot.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
import time

@dataclass
class Snapshot:
    """Единый снимок состояния для оркестратора."""
    has_window: bool
    alive: Optional[bool]              # True=жив, False=мертв, None=неизвестно
    hp_ratio: Optional[float]          # 0.0–1.0 или None
    respawn_enabled: bool
    autofarm_enabled: bool
    has_focus: Optional[bool]          # True=есть фокус, False=нет, None=неизвестно
    focus_unfocused_for_s: Optional[float]  # сколько секунд окно без фокуса (если известно)
    extras: Dict[str, Any] = None

def build_snapshot(sys_state: Dict[str, Any], _ps_adapter) -> Snapshot:
    """
    Источник правды:
      - player_state (hp/alive)
      - window_focus (фокус окна)
    """
    win = sys_state.get("window")
    has_window = bool(win and win.get("width") and win.get("height"))

    st = _ps_adapter.last() or {}
    alive = st.get("alive", None)
    try:
        hp_ratio = float(st.get("hp_ratio")) if st.get("hp_ratio") is not None else None
    except Exception:
        hp_ratio = None

    wf_last = sys_state.get("_wf_last") or {}
    has_focus = wf_last.get("has_focus", None)
    ts = float(wf_last.get("ts") or 0.0)
    unfocused_for = None
    if has_focus is False and ts > 0:
        unfocused_for = max(0.0, time.time() - ts)

    return Snapshot(
        has_window=has_window,
        alive=alive,
        hp_ratio=hp_ratio,
        respawn_enabled=bool(sys_state.get("respawn_enabled")),
        autofarm_enabled=bool(sys_state.get("af_enabled")),
        has_focus=has_focus,
        focus_unfocused_for_s=unfocused_for,
        extras={}
    )
