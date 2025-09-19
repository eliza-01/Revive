# core/engines/player_state/rules_runner.py
from __future__ import annotations
from typing import Any, List
import threading
import time

from core.logging import console
from core.engines.player_state.rules_engine import PlayerStateRulesEngine


class PlayerStateRulesRunner:
    """
    Лёгкий тикер для выполнения PS-правил отдельно от общего оркестратора.
    Никаких записей в пул сам по себе не делает — это делают сами правила.
    """

    def __init__(self, engine: PlayerStateRulesEngine, *, period_ms: int = 250):
        self.engine = engine
        self._period = max(50, int(period_ms))
        self._thr: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, name="PlayerStateRulesRunner", daemon=True)
        self._thr.start()
        console.log("[ps.rules] runner started")

    def stop(self, timeout: float = 0.5):
        try:
            self._stop.set()
            if self._thr:
                self._thr.join(timeout)
        finally:
            self._thr = None
            console.log("[ps.rules] runner stopped")

    def _loop(self):
        rules: List[Any] = self.engine.get_rules()
        next_tick = time.time()
        while not self._stop.is_set():
            now = time.time()
            if now >= next_tick:
                try:
                    # snap можно передавать при необходимости; текущие правила читают пул напрямую
                    snap = None
                    for r in rules:
                        try:
                            if hasattr(r, "when"):
                                if not r.when(snap):
                                    continue
                            if hasattr(r, "run"):
                                r.run(snap)
                        except Exception as e:
                            console.log(f"[ps.rules] rule error: {e}")
                except Exception as e:
                    console.log(f"[ps.rules] loop error: {e}")
                next_tick = now + self._period / 1000.0
            self._stop.wait(0.01)
