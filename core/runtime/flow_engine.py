# core/runtime/flow_engine.py
# """Generic flow engine with retry and restart logic."""
from __future__ import annotations
import time
from typing import Callable, Dict, List, Any


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


class FlowExecutor:
    """Default step executor used by Buff/TP workers."""

    def __init__(self, ctx: Any):
        self.ctx = ctx

    def __call__(self, step: Dict, idx: int, total: int) -> bool:
        tag = getattr(self.ctx, "_tag", "[flow]")
        op = step.get("op")
        thr = float(step.get("thr", getattr(self.ctx, "click_threshold", 0.87)))
        self.ctx._log(f"{tag}[step {idx}/{total}] {op}: {step}")

        if op == "click_any":
            ok = self.ctx._click_any(tuple(step["zones"]), step["tpl"], int(step["timeout_ms"]), thr)
            self.ctx._log(f"{tag}[step {idx}] result: {'OK' if ok else 'FAIL'}")
            if not ok:
                self.ctx._on_status(f"{tag} click_any fail: {step}", False)
            return ok

        elif op == "wait":
            ok = self.ctx._wait_template(step["zone"], step["tpl"], int(step["timeout_ms"]), thr)
            self.ctx._log(f"{tag}[step {idx}] result: {'OK' if ok else 'FAIL'}")
            if not ok:
                self.ctx._on_status(f"{tag} wait fail: {step}", False)
            return ok

        elif op == "dashboard_is_locked":
            zone_key = step["zone"]
            tpl_key = step["tpl"]
            timeout_ms = int(step.get("timeout_ms", 12000))
            interval_s = float(step.get("probe_interval_s", 1.0))

            start_ts = time.time()
            next_probe = 0.0
            unlocked = False

            while (time.time() - start_ts) * 1000.0 < timeout_ms:
                if getattr(self.ctx, "_is_dead", lambda: False)():
                    break

                locked_now = self.ctx._is_visible(zone_key, tpl_key, thr)
                if not locked_now:
                    unlocked = True
                    break

                now = time.time()
                if now >= next_probe:
                    self.ctx._log(f"{tag}[step {idx}] locked → probe left-click")
                    self.ctx._probe_left_click()
                    next_probe = now + interval_s

                time.sleep(0.08)

            self.ctx._log(f"{tag}[step {idx}] unlocked: {'YES' if unlocked else 'NO'}")
            if not unlocked:
                self.ctx._on_status(f"{tag} dashboard still locked", False)
            return unlocked

        elif op == "click_in":
            tpl_key = step["tpl"]
            if tpl_key == "{mode_key}" and hasattr(self.ctx, "_mode_tpl_key"):
                tpl_key = self.ctx._mode_tpl_key()
            ok = self.ctx._click_in(step["zone"], tpl_key, int(step["timeout_ms"]), thr)
            self.ctx._log(f"{tag}[step {idx}] result: {'OK' if ok else 'FAIL'}")
            if not ok:
                self.ctx._on_status(f"{tag} click_in fail: {step}", False)
            return ok

        elif op == "optional_click":
            ok = self.ctx._click_in(step["zone"], step["tpl"], int(step.get("timeout_ms", 800)), thr)
            self.ctx._log(f"{tag}[step {idx}] result: {'CLICKED' if ok else 'SKIP'}")
            return True

        elif op == "click_village" and hasattr(self.ctx, "_click_village"):
            ok = self.ctx._click_village(step)
            self.ctx._log(f"{tag}[step {idx}] click village → {'OK' if ok else 'FAIL'}")
            return ok

        elif op == "click_location" and hasattr(self.ctx, "_click_location"):
            ok = self.ctx._click_location(step)
            self.ctx._log(f"{tag}[step {idx}] click location → {'OK' if ok else 'FAIL'}")
            return ok

        elif op == "sleep":
            ms = int(step.get("ms", 50))
            self.ctx._log(f"{tag}[step {idx}] sleeping {ms} ms")
            time.sleep(ms / 1000.0)
            return True

        elif op == "send_arduino":
            cmd = step.get("cmd", "")
            delay_ms = int(step.get("delay_ms", 100))
            self.ctx._log(f"{tag}[step {idx}] send_arduino '{cmd}', delay {delay_ms} ms")
            self.ctx.controller.send(cmd)
            time.sleep(delay_ms / 1000.0)
            return True

        else:
            self.ctx._log(f"{tag}[step {idx}] unknown op: {op}")
            self.ctx._on_status(f"{tag} unknown op: {op}", False)
            return False

