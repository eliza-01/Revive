from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import time

from core.orchestrators.snapshot import Snapshot
from core.engines.respawn.runner import RespawnRunner
from core.engines.macros.runner import run_macros

class PipelineRule:
    """
    Единый оркестратор-пайплайн. Порядок шагов задаётся в sys_state["pipeline_order"].
    Поддерживает паузу по фокусу: без фокуса не стартует и не продвигает шаги.
    Сохраняет прогресс (индекс шага) и продолжает после возврата фокуса.
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

        # ленивые хелперы
        self._respawn_runner = RespawnRunner(
            engine=self._make_respawn_engine(),
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s.get("language") or "rus",
        )

    # ---------- lifecycle ----------
    def when(self, snap: Snapshot) -> bool:
        now = time.time()
        if now < self._busy_until or self._running:
            return False

        # пауза по фокусу: не запускаем/не двигаем, пока нет фокуса
        if snap.has_focus is False:
            return False

        order = self._order()
        if not order:
            return False

        # Активировать пайплайн: детект "мы мёртвые" + включен авто-респавн
        if not self._active:
            if (snap.alive is False) and bool(self.s.get("respawn_enabled", False)) and snap.has_window:
                self._active = True
                self._idx = 0
                self.report("[PIPE] старт пайплайна после смерти")
                return True
            return False

        # Уже активен — нужно выполнить/продвинуть текущий шаг
        return True

    def run(self, snap: Snapshot) -> None:
        self._running = True
        try:
            order = self._order()
            # страховка
            if not order:
                self._active = False
                return

            # если вылетели за границы — считаем завершением
            if self._idx >= len(order):
                self._finish()
                return

            step = order[self._idx]

            # шаги исполняем строго по имени
            ok, advance = self._run_step(step, snap)

            # если был выполнен — переходим к следующему
            if ok and advance:
                self._idx += 1
                # мягкий cooldown между шагами
                self._busy_until = time.time() + 0.5

            # если все прошли
            if self._idx >= len(order):
                self._finish()

        finally:
            self._running = False

    # ---------- steps ----------
    def _run_step(self, step: str, snap: Snapshot) -> tuple[bool, bool]:
        """
        Возвращает (ok, advance):
          ok=True  — шаг отработал без ошибок,
          advance=True — можно переходить к следующему.
        """
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

        # неизвестный шаг — пропускаем
        self.report(f"[PIPE] неизвестный шаг: {step} — пропуск")
        return True, True

    def _step_respawn(self, snap: Snapshot) -> tuple[bool, bool]:
        # не начинать без окна
        if not snap.has_window:
            return False, False
        # если уже жив — шаг считается успешным
        if snap.alive is True:
            return True, True

        # ожидание «ждать возрождения»
        wait_enabled = bool(self.s.get("respawn_wait_enabled"))
        wait_seconds = int(self.s.get("respawn_wait_seconds", 0))
        if wait_enabled and wait_seconds > 0:
            start = time.time()
            deadline = start + wait_seconds
            tick = -1
            while time.time() < deadline:
                # пауза по фокусу внутри шага
                if (self.s.get("_wf_last") or {}).get("has_focus") is False:
                    return False, False
                st = self.ps.last() or {}
                if st.get("alive"):
                    self.report("[RESPAWN] поднялись в ожидании")
                    self._toast("respawn", "Поднялись (ожидание)", True)
                    return True, True
                sec = int(time.time() - start)
                if sec != tick:
                    tick = sec
                    self.report(f"[RESPAWN] ожидание возрождения… {sec}/{wait_seconds}")
                time.sleep(1.0)

        # активная попытка
        self.report("[RESPAWN] активная попытка восстановления…")
        # не стартуем без фокуса
        if (self.s.get("_wf_last") or {}).get("has_focus") is False:
            return False, False

        # актуализируем сервер в движке
        try:
            self._respawn_runner.set_server(self.s.get("server") or "boh")
        except Exception:
            pass

        ok = bool(self._respawn_runner.run(timeout_ms=14_000))
        return (ok, ok)

    def _step_buff(self, snap: Snapshot) -> tuple[bool, bool]:
        # выключено — считаем пройденным
        if not bool(self.s.get("buff_enabled", False)):
            return True, True
        # не начинать без фокуса
        if (self.s.get("_wf_last") or {}).get("has_focus") is False:
            return False, False
        # TODO: здесь вызов вашего движка бафа (dashboard)
        # пока — заглушка-успех:
        self._toast("buff", "Баф выполнен (stub)", True)
        return True, True

    def _step_tp(self, snap: Snapshot) -> tuple[bool, bool]:
        if not bool(self.s.get("tp_enabled", False)):
            return True, True
        if (self.s.get("_wf_last") or {}).get("has_focus") is False:
            return False, False
        # TODO: здесь запуск ТП через dashboard
        self._toast("tp", "ТП выполнено (stub)", True)
        return True, True

    def _step_macros(self, snap: Snapshot) -> tuple[bool, bool]:
        # макросы в пайплайне не зависят от флага macros_enabled — порядок задаёт сам пайплайн
        rows = list(self.s.get("macros_rows") or [])
        if not rows:
            # наследуемся от legacy, если пусто
            seq = list(self.s.get("macros_sequence") or ["1"])
            dur = int(float(self.s.get("macros_duration_s", 0)))
            rows = [{"key": str(k)[:1], "cast_s": max(0, dur), "repeat_s": 0} for k in seq]

        # не начинать без фокуса
        if (self.s.get("_wf_last") or {}).get("has_focus") is False:
            return False, False

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
            # прерывание по потере фокуса
            should_abort=lambda: ((self.s.get("_wf_last") or {}).get("has_focus") is False),
        )
        return (bool(ok), bool(ok))

    def _step_autofarm(self, snap: Snapshot) -> tuple[bool, bool]:
        if not bool(self.s.get("af_enabled", False)):
            return True, True
        if (self.s.get("_wf_last") or {}).get("has_focus") is False:
            return False, False
        # TODO: запуск автофарма
        self._toast("autofarm", "Автофарм запущен (stub)", True)
        return True, True

    # ---------- utils ----------
    def _order(self) -> List[str]:
        # фиксируем, что respawn всегда первый и неизменяемый
        raw = list(self.s.get("pipeline_order") or [])
        if not raw:
            raw = ["respawn", "macros"]  # дефолт
        # гарантия, что respawn на позиции 0
        rest = [x for x in raw if x and x.lower() != "respawn"]
        return ["respawn"] + rest

    def _make_respawn_engine(self):
        # создаём движок как в старом respawn_rule
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
        self._active = False
        self._idx = 0
        self._busy_until = time.time() + 1.0


def make_pipeline_rule(sys_state, ps_adapter, controller, report: Optional[Callable[[str], None]] = None):
    return PipelineRule(sys_state, ps_adapter, controller, report or (lambda _m: None))
