# core/runtime/archive/state_bus.py
from __future__ import annotations
import threading, time
from dataclasses import dataclass
from typing import Callable, Optional, List

@dataclass
class AgentState:
    hp_ratio: float = 1.0
    alive: bool = True
    charged: Optional[bool] = None   # None=неизвестно, False=not_charged, True=charged
    updated_at: float = 0.0

class StateBus:
    def __init__(self):
        self._lock = threading.RLock()
        self._state = AgentState(updated_at=time.time())
        self._subs: List[Callable[[AgentState], None]] = []

    def get(self) -> AgentState:
        with self._lock:
            return self._state

    def update(self, **fields) -> AgentState:
        with self._lock:
            for k,v in fields.items():
                setattr(self._state, k, v)
            self._state.updated_at = time.time()
            st = self._state
        self._notify(st)
        return st

    def subscribe(self, cb: Callable[[AgentState], None]) -> None:
        with self._lock:
            self._subs.append(cb)

    def _notify(self, st: AgentState):
        for cb in list(self._subs):
            try: cb(st)
            except: pass
