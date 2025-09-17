# core/engines/coordinator/rules.py
from __future__ import annotations
from typing import Tuple, Protocol, Dict, Any, Optional
import time

from core.state.pool import pool_get


class ReasonProvider(Protocol):
    name: str
    def evaluate(self, state: Dict[str, Any], now: float) -> Tuple[str, bool]: ...


class UnfocusedReason:
    """
    Активируется, если окно без фокуса ≥ grace_seconds.
    Ведёт собственный таймер 'unfocused_since', чтобы исключить дребезг
    из-за внешних перезаписей focus.ts.
    """
    def __init__(self, grace_seconds: float = 0.4):
        self.name = "unfocused"
        self._grace = float(grace_seconds)
        self._unfocused_since: Optional[float] = None  # локальная память

    def evaluate(self, state: Dict[str, Any], now: float):
        is_focused = pool_get(state, "focus.is_focused", None)

        if is_focused is False:
            # зафиксировать старт «без фокуса» один раз
            if self._unfocused_since is None:
                # можно подсмотреть фолбек из пула, но не обязателен
                ts = float(pool_get(state, "focus.ts", 0.0) or 0.0)
                self._unfocused_since = ts if ts > 0.0 and ts <= now else now
            active = (now - (self._unfocused_since or now)) >= self._grace
        else:
            # вернулся фокус — сбросить счётчик
            self._unfocused_since = None
            active = False

        return self.name, bool(active)


class UiGuardReason:
    """Активируется, когда UI-сторож занят (busy)."""
    def __init__(self):
        self.name = "ui_guard"

    def evaluate(self, state: Dict[str, Any], now: float):
        busy = bool(pool_get(state, "features.ui_guard.busy", False))
        return self.name, busy
