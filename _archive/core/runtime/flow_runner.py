# core/runtime/flow_runner.py
from __future__ import annotations
from typing import Callable, Dict, List

class FlowRunner:
    def __init__(self, steps: Dict[str, Callable[[], None]], order: List[str]):
        self._steps = steps
        self._order = list(order)

    def run(self):
        for name in self._order:
            fn = self._steps.get(name)
            if callable(fn):
                try:
                    fn()
                except Exception as e:
                    print(f"[flow] step '{name}' error: {e}")
