from __future__ import annotations
from typing import Any, Dict, Iterable
from core.orchestrators.runtime import orchestrator_tick

class OrchestratorLoop:
    """
    Обёртка над orchestrator_tick с периодическим вызовом.
    Использует предоставленный schedule(fn, ms).
    """
    def __init__(self, state: Dict[str, Any], ps_adapter, rules: Iterable, schedule, period_ms: int = 2222):
        self._state = state
        self._ps_adapter = ps_adapter
        self._rules = list(rules)
        self._schedule = schedule
        self._period_ms = int(period_ms)
        self._stopped = False

    def _tick(self):
        if self._stopped:
            return
        try:
            orchestrator_tick(self._state, self._ps_adapter, self._rules)
        except Exception as e:
            print("[orch] tick error:", e)
        finally:
            if not self._stopped:
                self._schedule(self._tick, self._period_ms)

    def start(self):
        self._stopped = False
        self._schedule(self._tick, self._period_ms)

    def stop(self):
        self._stopped = True
