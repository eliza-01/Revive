# core/orchestrators/pipeline_rule.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional, List
import time
import importlib

from core.orchestrators.snapshot import Snapshot
from core.engines.respawn.runner import RespawnRunner
from core.engines.macros.runner import run_macros

from core.state.pool import pool_get, pool_merge


class PipelineRule:
    """
    Единый оркестратор-пайплайн.
    Порядок шагов читается из пула: pipeline.order.
    Работает независимо от фокуса (пауза/резюм — отдельным правилом).
    """

    def __init__(self, state: Dict[str, Any], ps_adapter, controller, report: Callable[[str], None]):
        self.s = state
        self.ps = ps_adapter
        self.controller = controller
        self.report = report

        self._active = False
        self._idx = 0
        self._running = False
        self._busy_until = 0.0

        self._respawn_runner = RespawnRunner(
            engine=self._make_respawn_engine(),
            get_window=lambda: pool_get(self.s, "window.info", None),
            get_language=lambda: pool_get(self.s, "config.language", "rus"),
        )

    # --- util debug ---
    def _dbg(self, msg: str):
        if pool_get(self.s, "runtime.debug.respawn_debug", False) or pool_get(self.s, "runtime.debug.pipeline_debug", False):
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

        # Корректный детект смерти
        is_dead = (snap.alive is False) or (snap.hp_ratio is not None and snap.hp_ratio <= 0.001)

        # Тумблер авто-респавна — только из пула
        respawn_on = bool(pool_get(self.s, "features.respawn.enabled", False))

        # Дебаг по тику оркестратора
        macros_on = bool(pool_get(self.s, "features.macros.enabled", False))
        self._dbg(
            "tick: "
            f"win={snap.has_window} "
            f"focus={snap.has_focus} "
            f"alive={snap.alive} is_dead={is_dead} hp={snap.hp_ratio} "
            f"respawn={respawn_on} macros={macros_on} active={self._active} idx={self._idx}"
        )
        self._dbg("----------------------------------------")

        # Смерть есть, окно есть, а авто-респавн выключен — сообщим и подождём
        if (not self._active) and is_dead and (not respawn_on) and snap.has_window:
            self._dbg("no-activate: dead but respawn disabled")
            self.report("[PIPE] смерть обнаружена, но авто-респавн выключен")
            self._busy_until = time.time() + 2.0
            return False

        # Активировать пайплайн
        if not self._active:
            if is_dead and respawn_on and snap.has_window:
                self._active = True
                self._idx = 0
                pool_merge(self.s, "pipeline", {"active": True, "idx": 0, "last_step": ""})
                self._dbg(f"activate: dead={is_dead} alive={snap.alive} hp={snap.hp_ratio}")
                self.report("[PIPE] старт пайплайна после смерти")
                return True
            return False

        # уже активен — двигаем шаг
        return True

    def run(self, snap: Snapshot) -> None:
        self._running = True
        try:
            order = self._order()
            if not order:
                self._dbg("finish: empty order at run()")
                self._finish()
                return

            if self._idx >= len(order):
                self._dbg("finish: idx>=len(order)")
                self._finish()
                return

            step = order[self._idx]
            self._dbg(f"run step[{self._idx}]: {step}")
            pool_merge(self.s, "pipeline", {"active": True, "idx": self._idx, "last_step": step})

            ok, advance = self._run_step(step, snap)

            self._dbg(f"step result: ok={ok} advance={advance}")
            if ok and advance:
                self._idx += 1
                pool_merge(self.s, "pipeline", {"idx": self._idx})
                self._busy_until = time.time() + 0.5
                self._dbg(f"advance -> idx={self._idx}")

            if self._idx >= len(order):
                self._finish()

        finally:
            self._running = False

    # ---------- steps ----------

    def _is_step_enabled(self, step: str) -> bool:
        """
        Единообразно читаем тумблеры только из пула.
        """
        feature = {
            "respawn": "respawn",
            "buff": "buff",
            "tp": "tp",
            "macros": "macros",
            "autofarm": "autofarm",
        }.get(step)
        if not feature:
            return True
        return bool(pool_get(self.s, f"features.{feature}.enabled", False))

    def _run_step(self, step: str, snap: Snapshot) -> tuple[bool, bool]:
        step = (step or "").lower().strip()

        # Уважаем тумблер шага
        if not self._is_step_enabled(step):
            self._dbg(f"{step}: disabled -> pass")
            return True, True

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

        self._dbg(f"unknown step: {step}")
        self.report(f"[PIPE] неизвестный шаг: {step} — пропуск")
        return True, True

    def _step_respawn(self, snap: Snapshot) -> tuple[bool, bool]:
        # не начинать без окна
        if not snap.has_window:
            self._dbg("respawn: no window")
            return False, False

        # если уже жив — шаг успешен и идём дальше
        if snap.alive is True:
            self._dbg("respawn: already alive")
            return True, True

        # опциональное ожидание «ждать возрождения» — из пула
        wait_enabled = bool(pool_get(self.s, "features.respawn.wait_enabled", False))
        wait_seconds = int(pool_get(self.s, "features.respawn.wait_seconds", 0))
        if wait_enabled and wait_seconds > 0:
            start = time.time()
            deadline = start + wait_seconds
            tick = -1
            while time.time() < deadline:
                st = self.ps.last() or {}
                if st.get("alive"):
                    self.report("[RESPAWN] Поднялись (ожидание)")
                    self._dbg("respawn/wait: alive -> success")
                    return True, True
                sec = int(time.time() - start)
                if sec != tick:
                    tick = sec
                    self.report(f"[RESPAWN] ожидание возрождения… {sec}/{wait_seconds}")
                time.sleep(1.0)

        # активная попытка восстановления
        self.report("[RESPAWN] Активная попытка восстановления…")
        try:
            self._respawn_runner.set_server(pool_get(self.s, "config.server", "boh"))
        except Exception:
            pass

        ok = bool(self._respawn_runner.run(timeout_ms=14_000))
        self._dbg(f"respawn: result ok={ok}")
        return (ok, ok)

    def _step_buff(self, snap: Snapshot) -> tuple[bool, bool]:
        self.report("[BUFF] выполнен (stub)")
        self._dbg("buff: stub ok")
        return True, True

    def _step_tp(self, snap: Snapshot) -> tuple[bool, bool]:
        self.report("[TP] выполнено (stub)")
        self._dbg("tp: stub ok")
        return True, True

    def _step_macros(self, snap: Snapshot) -> tuple[bool, bool]:
        rows = list(pool_get(self.s, "features.macros.rows", []) or [])
        if not rows:
            seq = list(pool_get(self.s, "features.macros.sequence", ["1"]) or ["1"])
            dur = int(float(pool_get(self.s, "features.macros.duration_s", 0)))
            rows = [{"key": str(k)[:1], "cast_s": max(0, dur), "repeat_s": 0} for k in seq]

        def _status(text: str, ok: Optional[bool] = None):
            self.report(f"[MACROS] {text}")

        ok = run_macros(
            server=pool_get(self.s, "config.server", "boh"),
            controller=self.controller,
            get_window=lambda: pool_get(self.s, "window.info", None),
            get_language=lambda: pool_get(self.s, "config.language", "rus"),
            on_status=_status,
            cfg={"rows": rows},
            should_abort=lambda: False,
        )
        self._dbg(f"macros: result ok={ok}")

        # после успешного «ручного» прогона — сдвигаем таймер повтора (если сервис доступен в контейнере)
        try:
            if ok:
                svc = (self.s.get("_services") or {}).get("macros_repeat")
                if hasattr(svc, "bump_all"):
                    svc.bump_all()
        except Exception:
            pass

        return (bool(ok), bool(ok))

    def _step_autofarm(self, snap: Snapshot) -> tuple[bool, bool]:
        self.report("Автофарм запущен (stub)")
        self._dbg("autofarm: stub ok")
        return True, True

    # ---------- utils ----------
    def _order(self) -> List[str]:
        """
        Порядок читаем только из пула.
        Респавн держим первым — страховка от случайных перестановок.
        """
        raw = list(pool_get(self.s, "pipeline.order", ["respawn", "macros"]) or [])
        if not raw:
            raw = ["respawn", "macros"]
        rest = [x for x in raw if x and x.lower() != "respawn"]
        return ["respawn"] + rest

    def _load_respawn_module(self, server: str):
        """
        Динамически загружает модуль движка респавна:
        core.engines.respawn.server.<server>.engine
        Фолбэк: core.engines.respawn.server.boh.engine (если серверный модуль не найден).
        """
        server = (server or "boh").lower()
        module_name = f"core.engines.respawn.server.{server}.engine"
        try:
            return importlib.import_module(module_name)
        except Exception:
            # мягкий фолбэк
            try:
                return importlib.import_module("core.engines.respawn.server.boh.engine")
            except Exception as e:
                raise ImportError(f"Respawn engine module not found for '{server}' and fallback 'boh': {e}") from e

    def _make_respawn_engine(self):
        mod = self._load_respawn_module(pool_get(self.s, "config.server", "boh"))

        create_engine = getattr(mod, "create_engine", None)
        RespawnEngine = getattr(mod, "RespawnEngine", None)

        # общие параметры из пула
        server = pool_get(self.s, "config.server", "boh")
        click_threshold = float(pool_get(self.s, "features.respawn.click_threshold", 0.70))
        confirm_timeout_s = float(pool_get(self.s, "features.respawn.confirm_timeout_s", 6.0))
        debug = bool(pool_get(self.s, "runtime.debug.respawn_debug", False))

        def _is_alive():
            try:
                st = self.ps.last() or {}
                return bool(st.get("alive"))
            except Exception:
                return True

        def _on_engine_report(code: str, text: str):
            self.report(f"[RESPAWN] {text}")

        if callable(create_engine):
            return create_engine(
                server=server,
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=click_threshold,
                confirm_timeout_s=confirm_timeout_s,
                debug=debug,
                on_report=_on_engine_report,
            )
        elif RespawnEngine is not None:
            return RespawnEngine(
                server=server,
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=click_threshold,
                confirm_timeout_s=confirm_timeout_s,
                debug=debug,
                on_report=_on_engine_report,
            )
        else:
            # крайний случай — явно падаем, чтобы было видно проблему с серверным модулем
            raise RuntimeError("Respawn engine class/factory not found in loaded module")

    def _finish(self):
        self.report("[PIPE] пайплайн завершён")
        self._dbg("finish: reset state")
        self._active = False
        self._idx = 0
        self._busy_until = time.time() + 1.0
        pool_merge(self.s, "pipeline", {"active": False, "idx": 0})


def make_pipeline_rule(state, ps_adapter, controller, report: Optional[Callable[[str], None]] = None):
    return PipelineRule(state, ps_adapter, controller, report or (lambda _m: None))
