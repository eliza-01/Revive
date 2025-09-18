from __future__ import annotations
from typing import Tuple, Protocol, Dict, Any, Optional

from core.state.pool import pool_get


class ReasonProvider(Protocol):
    name: str
    def evaluate(self, state: Dict[str, Any], now: float) -> Tuple[str, bool]: ...


class UnfocusedReason:
    """
    Активируется, если окно без фокуса ≥ grace_seconds.
    Ведёт собственный таймер 'unfocused_since', чтобы исключить дребезг.
    """
    def __init__(self, grace_seconds: float = 0.4):
        self.name = "unfocused"
        self._grace = float(grace_seconds)
        self._unfocused_since: Optional[float] = None  # локальная память

    def evaluate(self, state: Dict[str, Any], now: float):
        is_focused = pool_get(state, "focus.is_focused", None)

        if is_focused is False:
            if self._unfocused_since is None:
                ts = float(pool_get(state, "focus.ts", 0.0) or 0.0)
                self._unfocused_since = ts if ts > 0.0 and ts <= now else now
            active = (now - (self._unfocused_since or now)) >= self._grace
        else:
            self._unfocused_since = None
            active = False

        return self.name, bool(active)


class UiGuardReason:
    """Активируется, когда UI-сторож занят (busy=True)."""
    def __init__(self):
        self.name = "ui_guard"

    def evaluate(self, state: Dict[str, Any], now: float):
        busy = bool(pool_get(state, "features.ui_guard.busy", False))
        return self.name, busy


class Cor1Reason:
    """
    cor_1:
      окно без фокуса И ui_guard не занят
    """
    def __init__(self):
        self.name = "cor_1"

    def evaluate(self, state: Dict[str, Any], now: float):
        focused = bool(pool_get(state, "focus.is_focused", True))
        ui_busy = bool(pool_get(state, "features.ui_guard.busy", False))
        return self.name, (focused is False and not ui_busy)


class Cor2Reason:
    """
    cor_2:
      alive=True И hp_ratio=None И features.autofarm.busy=True
    """
    def __init__(self):
        self.name = "cor_2"

    def evaluate(self, state: Dict[str, Any], now: float):
        alive = bool(pool_get(state, "player.alive", False))
        hp_none = (pool_get(state, "player.hp_ratio", None) is None)
        af_busy = bool(pool_get(state, "features.autofarm.busy", False))
        return self.name, bool(alive and hp_none and af_busy)


class Cor3Reason:
    """
    cor_3:
      ui_guard.busy=True И окно без фокуса → приостанавливаем сам ui_guard
    """
    def __init__(self):
        self.name = "cor_3"

    def evaluate(self, state: Dict[str, Any], now: float):
        focused = bool(pool_get(state, "focus.is_focused", True))
        ui_busy = bool(pool_get(state, "features.ui_guard.busy", False))
        return self.name, (ui_busy and (focused is False))
