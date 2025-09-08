# core/orchestrators/pipeline_rule.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import time

from core.orchestrators.snapshot import Snapshot
from core.engines.macros.runner import run_macros
from core.engines.respawn.server.boh.orchestrator_rules import make_respawn_rule

class _PipelineRule:
    def __init__(self, s: Dict[str, Any], controller, ps_adapter, report: Callable[[str], None]):
        self.s = s
        self.controller = controller
        self.ps = ps_adapter
        self.report = report
        self._running = False
        self._busy_until = 0.0

    def when(self, snap: Snapshot) -> bool:
        now = time.time()
        if now < self._busy_until or self._running:
            return False
        if not bool(self.s.get("pipeline_enabled", True)):
            return False
        if not snap.has_window:
            return False
        # Триггер — смерть
        return (snap.alive is False)

    def run(self, snap: Snapshot) -> None:
        self._running = True
        try:
            order: List[str] = list(self.s.get("pipeline_order") or ["respawn","macros"])
            # 1) Respawn (фиксирован)
            if not self._step_respawn():
                self._busy_until = time.time() + 4.0
                return

            # 2) Остальные по порядку
            for step in order:
                if step == "respawn":
                    continue
                if step == "macros":
                    if not self._step_macros_once():
                        break
                elif step == "buff":
                    # TODO: подключить ваш buff runner, сейчас пропускаем как OK
                    pass
                elif step == "tp":
                    # TODO: подключить tp runner, сейчас пропускаем как OK
                    pass
                elif step == "autofarm":
                    # TODO: старт/разморозка автофарма, если требуется
                    pass

            self._busy_until = time.time() + 2.0
        finally:
            self._running = False

    # --- шаги ---
    def _step_respawn(self) -> bool:
        self.report("[PIPE] Respawn…")
        # используем готовое правило респавна как «исполнитель одного шага»
        # (оно читает из self.s нужные настройки)
        rr = make_respawn_rule(self.s, self.ps, self.controller, report=self.report)
        # Эмулируем его when→run: просто вызвать run
        try:
            rr.run(None)   # снап не нужен внутри
            # читаем состояние alive; если жив — успех
            return bool(self.ps.is_alive())
        except Exception:
            return False

    def _step_macros_once(self) -> bool:
        rows = list(self.s.get("macros_rows") or [])
        if not rows:
            self.report("[PIPE] Макросы: пусто — пропуск")
            return True

        self.report("[PIPE] Макросы (разово)…")
        ok = run_macros(
            server=(self.s.get("server") or "boh"),
            controller=self.controller,
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s.get("language") or "rus",
            on_status=lambda txt, ok=None: self._emit_ui("macros", txt, ok),
            cfg={"rows": rows},
            should_abort=lambda: False,
        )
        # Разрешим повторы после первого удачного прогона
        if ok:
            self.s["_macros_initial_done"] = True
        return bool(ok)

    def _emit_ui(self, scope: str, text: str, ok: Optional[bool]):
        try:
            emit = self.s.get("ui_emit")
            if callable(emit):
                emit(scope, text, ok)
        except Exception:
            pass

def make_pipeline_rule(sys_state, controller, ps_adapter, report: Optional[Callable[[str], None]] = None):
    return _PipelineRule(sys_state, controller, ps_adapter, report or (lambda _m: None))
