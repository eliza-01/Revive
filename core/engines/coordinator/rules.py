# core/engines/coordinator/rules.py
from __future__ import annotations
from typing import Tuple, Protocol, Dict, Any

from core.state.pool import pool_get


class ReasonProvider(Protocol):
    name: str
    def evaluate(self, state: Dict[str, Any], now: float) -> Tuple[str, bool]: ...


class Cor1Reason:
    """
    cor_1: окно без фокуса.
    Координатор запоминает, кого он сам поставил на паузу, и снимет паузу только с них.
    """
    def __init__(self):
        self.name = "cor_1"

    def evaluate(self, state: Dict[str, Any], now: float):
        focused = pool_get(state, "focus.is_focused", None)
        return self.name, (focused is False)


class Cor2Reason:
    """
    cor_2:
      alive=True И hp_ratio=None И features.autofarm.busy=True
    Координатор ставит паузу всем (кроме ui_guard) и "запускает" ui_guard.
    Снимет паузы только если ui_guard завершился и оставил pause_reason == "empty".
    Если ui_guard вернул непустую причину — выводим заглушку и оставляем паузы.
    """
    def __init__(self):
        self.name = "cor_2"

    def evaluate(self, state: Dict[str, Any], now: float):
        alive = bool(pool_get(state, "player.alive", False))
        hp_none = (pool_get(state, "player.hp_ratio", None) is None)
        af_busy = bool(pool_get(state, "features.autofarm.busy", False))
        return self.name, bool(alive and hp_none and af_busy)
