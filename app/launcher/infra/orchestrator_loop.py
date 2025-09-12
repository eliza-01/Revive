from __future__ import annotations
import threading
from typing import Any, Dict, List

from core.orchestrators.runtime import orchestrator_tick
from core.logging import console   # <-- добавлено: чтобы не ловить NameError в except


class OrchestratorLoop:
    def __init__(self, state: Dict[str, Any], ps_adapter, rules: List[Any], scheduler, period_ms: int = 2000):
        self._state = state
        self._ps_adapter = ps_adapter
        self._rules = rules
        self._scheduler = scheduler
        self._period = max(0.0, float(period_ms) / 1000.0)
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._schedule_next()

    def stop(self):
        self._running = False

    def _schedule_next(self):
        if not self._running:
            return
        # используем внешний планировщик из UI (ui.schedule)
        try:
            self._scheduler(self._tick, int(self._period * 1000))
        except Exception:
            # запасной вариант на threading.Timer
            t = threading.Timer(self._period, self._tick)
            t.daemon = True
            t.start()

    def _tick(self):
        try:
            orchestrator_tick(self._state, self._ps_adapter, self._rules)
        except Exception as e:
            # Был NameError из-за отсутствия импорта console — фиксим
            console.log(f"[orchestrator_loop.py] tick error: {e}")
        finally:
            self._schedule_next()
