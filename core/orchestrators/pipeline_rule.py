# core/orchestrators/pipeline_rule.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import time

from core.orchestrators.snapshot import Snapshot
from core.engines.respawn.runner import RespawnRunner
from core.engines.macros.runner import run_macros

class PipelineRule:
    """
    Единый оркестратор-пайплайн. Порядок шагов задаётся в sys_state["pipeline_order"].
    Не зависит от состояния фокуса. Сохраняет прогресс (индекс шага).
    """

    def __init__(self, s: Dict[str, Any], ps_adapter, controller, report: Callable[[str], None]):
        self.s = s
        self.ps = ps_adapter
        self.controller = controller
        self.report = report

        self._active = False
        self._idx = 0
        self._running = False
        self._busy_until = 0.0

        self._respawn_runner = RespawnRunner(
            engine=self._make_respawn_engine(),
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s.get("language") or "rus",
        )

    # --- util debug ---
    def _dbg(self, msg: str):
        if self.s.get("respawn_debug") or self.s.get("pipeline_debug"):
            try:
                print(f"[PIPE/DBG] {msg}")
            except Exception:
                pass

    # ---------- lifecycle ----------
    def when(self, snap: Snapshot) -> bool:
        now = time.time()
        if now < self._busy_until:
            self._dbg(f"skip: cooldown left {self._busy_until - now:.2f}s")
            return False
        if self._running:
            self._dbg("skip: already running")
            return False

        order = self._order()
        if not order:
            self._dbg("skip: empty order")
            return False

        # Корректный детект смерти:
        is_dead = (snap.alive is False) or (snap.hp_ratio is not None and snap.hp_ratio <= 0.001)
        respawn_on = bool(self.s.get("respawn_enabled", False))
        self._dbg(f"respawn_enabled={respawn_on} win={snap.has_window} alive={snap.alive} hp={snap.hp_ratio}")

        # Смерть есть, окно есть, а авто-респавн выключен — сообщим и подождём
        if (not self._active) and is_dead and (not respawn_on) and snap.has_window:
            self._dbg("no-activate: dead but respawn disabled")
            self.report("[PIPE] смерть обнаружена, но авто-респавн выключен")
            self._toast("respawn", "Авто-респавн выключен — включите в UI", None)
            self._busy_until = time.time() + 2.0
            return False

        # Активировать пайплайн
        if not self._active:
            if is_dead and respawn_on and snap.has_window:
                self._active = True
                self._idx = 0
                self._dbg(f"activate: dead={is_dead} alive={snap.alive} hp={snap.hp_ratio}")
                self.report("[PIPE] старт пайплайна после смерти")
                return True
            self._dbg(
                "no-activate:"
                f" dead={is_dead}"
                f" respawn={respawn_on}"
                f" has_window={snap.has_window}"
            )
            return False

        # уже активен — двигаем шаг
        return True

    def run(self, snap: Snapshot) -> None:
        self._running = True
        try:
            order = self._order()
            if not order:
                self._dbg("finish: empty order at run()")
                self._active = False
                return

            if self._idx >= len(order):
                self._dbg("finish: idx>=len(order)")
                self._finish()
                return

            step = order[self._idx]
            self._dbg(f"run step[{self._idx}]: {step}")

            ok, advance = self._run_step(step, snap)

            self._dbg(f"step result: ok={ok} advance={advance}")
            if ok and advance:
                self._idx += 1
                self._busy_until = time.time() + 0.5
                self._dbg(f"advance -> idx={self._idx}")

            if self._idx >= len(order):
                self._finish()

        finally:
            self._running = False

    # ---------- steps ----------
    def _run_step(self, step: str, snap: Snapshot) -> tuple[bool, bool]:
        step = (step or "").lower().strip()

        if step == "respawn":
            return self._step_respawn(snap)
        if step == "buff":
            return self._step_buff(snap)
        if step == "tp":
            return self._step_tp(snap)
        if step == "macros":
            return self._step_macros(snap)
        if step == "autofarm":
            return self._step_autofarm(snap)

        self.report(f"[PIPE] неизвестный шаг: {step} — пропуск")
        self._dbg(f"unknown step: {step}")
        return True, True

    def _step_respawn(self, snap: Snapshot) -> tuple[bool, bool]:
        if not snap.has_window:
            self._dbg("respawn: no window")
            return False, False
        if snap.alive is True:
            self._dbg("respawn: already alive")
            return True, True

        wait_enabled = bool(self.s.get("respawn_wait_enabled"))
        wait_seconds = int(self.s.get("respawn_wait_seconds", 0))
        if wait_enabled and wait_seconds > 0:
            start = time.time()
            deadline = start + wait_seconds
            tick = -1
            while time.time() < deadline:
                st = self.ps.last() or {}
                if st.get("alive"):
                    self.report("[RESPAWN] Поднялись (ожидание)")
                    self._toast("respawn", "Поднялись (ожидание)", True)
                    self._dbg("respawn/wait: alive -> success")
                    return True, True
                sec = int(time.time() - start)
                if sec != tick:
                    tick = sec
                    self.report(f"[RESPAWN] ожидание возрождения… {sec}/{wait_seconds}")
                time.sleep(1.0)

        self.report("[RESPAWN] Активная попытка восстановления…")

        try:
            self._respawn_runner.set_server(self.s.get("server") or "boh")
        except Exception:
            pass

        ok = bool(self._respawn_runner.run(timeout_ms=14_000))
        self._dbg(f"respawn: result ok={ok}")
        return (ok, ok)

    def _step_buff(self, snap: Snapshot) -> tuple[bool, bool]:
        if not bool(self.s.get("buff_enabled", False)):
            self._dbg("buff: disabled -> pass")
            return True, True
        self._toast("buff", "Баф выполнен (stub)", True)
        self._dbg("buff: stub ok")
        return True, True

    def _step_tp(self, snap: Snapshot) -> tuple[bool, bool]:
        if not bool(self.s.get("tp_enabled", False)):
            self._dbg("tp: disabled -> pass")
            return True, True
        self._toast("tp", "ТП выполнено (stub)", True)
        self._dbg("tp: stub ok")
        return True, True

    def _step_macros(self, snap: Snapshot) -> tuple[bool, bool]:
        rows = list(self.s.get("macros_rows") or [])
        if not rows:
            seq = list(self.s.get("macros_sequence") or ["1"])
            dur = int(float(self.s.get("macros_duration_s", 0)))
            rows = [{"key": str(k)[:1], "cast_s": max(0, dur), "repeat_s": 0} for k in seq]

        def _status(text: str, ok: Optional[bool] = None):
            self.report(f"[MACROS] {text}")
            self._toast("macros", text, ok)

        ok = run_macros(
            server=self.s.get("server") or "boh",
            controller=self.controller,
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s.get("language") or "rus",
            on_status=_status,
            cfg={"rows": rows},
            # Больше не прерываемся по фокусу
            should_abort=lambda: False,
        )
        self._dbg(f"macros: result ok={ok}")
        return (bool(ok), bool(ok))

    def _step_autofarm(self, snap: Snapshot) -> tuple[bool, bool]:
        if not bool(self.s.get("af_enabled", False)):
            self._dbg("autofarm: disabled -> pass")
            return True, True
        self._toast("autofarm", "Автофарм запущен (stub)", True)
        self._dbg("autofarm: stub ok")
        return True, True

    # ---------- utils ----------
    def _order(self) -> List[str]:
        raw = list(self.s.get("pipeline_order") or [])
        if not raw:
            raw = ["respawn", "macros"]
        rest = [x for x in raw if x and x.lower() != "respawn"]
        order = ["respawn"] + rest
        return order

    def _make_respawn_engine(self):
        try:
            from core.engines.respawn.server.boh.engine import create_engine as _create_engine
        except Exception:
            _create_engine = None
        from core.engines.respawn.server.boh.engine import RespawnEngine  # type: ignore

        def _is_alive():
            try:
                st = self.ps.last() or {}
                return bool(st.get("alive"))
            except Exception:
                return True

        def _on_engine_report(code: str, text: str):
            self.report(f"[RESPAWN] {text}")
            ok = True if code == "SUCCESS" else False if code.startswith("FAIL") or code.startswith("TIMEOUT") else None
            self._toast("respawn", text, ok)

        if _create_engine:
            return _create_engine(
                server=self.s.get("server") or "boh",
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=float(self.s.get("respawn_click_threshold", 0.70)),
                confirm_timeout_s=float(self.s.get("respawn_confirm_timeout_s", 6.0)),
                debug=bool(self.s.get("respawn_debug", True)),
                on_report=_on_engine_report,
            )
        else:
            return RespawnEngine(
                server=self.s.get("server") or "boh",
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=float(self.s.get("respawn_click_threshold", 0.70)),
                confirm_timeout_s=float(self.s.get("respawn_confirm_timeout_s", 6.0)),
                debug=bool(self.s.get("respawn_debug", True)),
                on_report=_on_engine_report,
            )

    def _toast(self, scope: str, text: str, ok: Optional[bool]):
        emit = self.s.get("ui_emit")
        if callable(emit):
            emit(scope, text, ok)

    def _finish(self):
        self.report("[PIPE] пайплайн завершён")
        self._dbg("finish: reset state")
        self._active = False
        self._idx = 0
        self._busy_until = time.time() + 1.0


def make_pipeline_rule(sys_state, ps_adapter, controller, report: Optional[Callable[[str], None]] = None):
    return PipelineRule(sys_state, ps_adapter, controller, report or (lambda _m: None))
