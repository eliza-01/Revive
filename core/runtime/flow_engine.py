# core/runtime/flow_engine.py
# """Generic flow engine with retry and restart logic."""
from __future__ import annotations
import time
from typing import Callable, Dict, List


class FlowEngine:
    """
    Execute a sequence of declarative steps.  Each step is interpreted by
    an external *executor* callable which receives the step dict and
    returns ``True`` on success or ``False`` on failure.

    Steps may contain the following optional keys:

    ``retry_count`` – how many times a failing step may be retried.
    ``retry_action`` – one of:
        ``"repeat"``  – retry the same step;
        ``"prev"``    – retry the previous step before repeating the current;
        ``"restart"`` – restart the whole flow.

    If retries are exhausted the engine stops and reports failure.
    """

    def __init__(self, flow: List[Dict], executor: Callable[[Dict, int, int], bool]):
        self._flow = list(flow or [])
        self._exec = executor

    # ------------------------------------------------------------------
    def run(self) -> bool:
        total = len(self._flow)
        attempts = [0] * total
        idx = 0

        while idx < total:
            step = self._flow[idx]
            ok = False
            try:
                ok = bool(self._exec(step, idx + 1, total))
            except Exception:
                ok = False

            if ok:
                attempts[idx] = 0
                idx += 1
                continue

            # failure – decide how to retry
            attempts[idx] += 1
            retries = int(step.get("retry_count", 0))
            if attempts[idx] <= retries:
                delay_ms = int(step.get("retry_delay_ms", 0))
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                action = (step.get("retry_action") or "repeat").lower()
                if action == "prev" and idx > 0:
                    attempts[idx] = 0  # reset current attempts
                    idx -= 1
                elif action == "restart":
                    attempts = [0] * total
                    idx = 0
                else:  # default: repeat current step
                    pass
                continue

            # no retries left
            return False

        return True
