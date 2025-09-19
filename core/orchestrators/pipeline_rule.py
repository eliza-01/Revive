# core/orchestrators/pipeline_rule.py
from __future__ import annotations
from typing import Any, Dict, List
import time
import importlib

from core.orchestrators.snapshot import Snapshot
from core.engines.respawn.runner import RespawnRunner
from core.engines.record.engine import RecordEngine

from core.state.pool import pool_get, pool_merge, pool_write
from core.logging import console


class PipelineRule:
    """
    Универсальный оркестратор-пайплайн.
    Следит за очередью шагов из пула (pipeline.order) и их завершением.
    Логику шагов (respawn/macros и др.) делегируем в server-специфичные rules.py.

    Репортов больше нет — сообщения уходим напрямую в HUD через console.hud.
    """

    def __init__(self, state: Dict[str, Any], ps_adapter, controller, helpers=None):
        self.s = state
        self.ps = ps_adapter
        self.controller = controller
        self._helpers = helpers or {}

        self._active = False
        self._idx = 0
        self._running = False
        self._busy_until = 0.0 #кулдаун. Метка, после которой можно снова работать.

        self._respawn_runner = RespawnRunner(
            engine=self._make_respawn_engine(),
            get_window=lambda: pool_get(self.s, "window.info", None),
            get_language=lambda: pool_get(self.s, "config.language", "rus"),
        )
        self._record_engine = RecordEngine(
            state=self.s,
            controller=self.controller,
            get_window=lambda: pool_get(self.s, "window.info", None),
        )
    # --- util debug / hud ---
    def _dbg(self, msg: str):
        try:
            pd = pool_get(self.s, "runtime.debug.pipeline_debug", False)
            if pd is True:  # ← только настоящий bool True
                console.log(f"[PIPE/DBG] {msg}")
        except Exception:
            pass

    def _set_busy(self, feature: str, on: bool):
        try:
            pool_write(self.s, f"features.{feature}", {"busy": bool(on)})
        except Exception:
            pass

    def _hud_ok(self, text: str):   console.hud("ok",   text)
    def _hud_succ(self, text: str): console.hud("succ", text)
    def _hud_err(self, text: str):  console.hud("err",  text)

    # --- helper ---
    # cooldown
    def _cd(self, secs: float):
        self._busy_until = time.time() + max(0.0, secs)
    # ---------- lifecycle ----------
    def when(self, snap: Snapshot) -> bool:

        if pool_get(self.s, "pipeline.paused", False):
            # опц.: логнуть причину
            pr = pool_get(self.s, "pipeline.pause_reason", "")
            console.log(f"[PIPE] pause: pipeline.paused ({pr})")
            return False

        if snap.is_focused is False:
            return False

        now = time.time()
        if now < self._busy_until:
            console.log(f"[PIPE] cooldown left {self._busy_until - now:.2f}s")
            return False
        if self._running:
            console.log("[PIPE] skip: already running")
            return False

        # === НОВОЕ: глобальные паузы вместо is_focused ===
        # 1) если UI-страж занят или в паузе — ждём
        if snap.extras.get("ui_guard_busy") or snap.extras.get("ui_guard_paused"):
            console.log("[PIPE] pause: ui_guard is busy/paused")
            return False
        # 2) если любая фича/сервис на паузе — ждём
        if snap.extras.get("any_feature_paused"):
            console.log("[PIPE] pause: some feature/service is paused")
            return False

        order = self._order()
        if not order:
            console.log("[PIPE] skip: empty order")
            return False

        # Корректный детект смерти
        is_dead = (snap.alive is False) or (snap.hp_ratio is not None and snap.hp_ratio <= 0.001)

        respawn_on = bool(pool_get(self.s, "features.respawn.enabled", False))
        macros_on  = bool(pool_get(self.s, "features.macros.enabled",  False))
        self._dbg(
            "tick: "
            f"alive={snap.alive} is_dead={is_dead} hp={snap.hp_ratio} "
            f"respawn={respawn_on} macros={macros_on} active={self._active} idx={self._idx}"
        )

        if (not self._active) and is_dead and (not respawn_on) and snap.has_window:
            console.log("[PIPE] no-activate: dead but respawn disabled")
            self._hud_err("[PIPE] смерть обнаружена, но авто-респавн выключен")
            self._cd(2.0)
            return False

        if not self._active:
            if is_dead and respawn_on and snap.has_window:
                self._active = True
                self._idx = 0
                pool_merge(self.s, "pipeline", {"active": True, "idx": 0, "last_step": "", "ts": time.time()})
                console.log(f"[PIPE] activate: dead={is_dead} alive={snap.alive} hp={snap.hp_ratio}")
                self._hud_succ("[PIPE] старт пайплайна после смерти")
                return True
            return False

        return True

    def run(self, snap: Snapshot) -> None:
        self._running = True
        try:
            order = self._order()
            if not order:
                console.log("[PIPE] finish: empty order at run()")
                self._finish()
                return

            if self._idx >= len(order):
                console.log("[PIPE] finish: idx>=len(order)")
                self._finish()
                return

            step = order[self._idx]
            console.log(f"[PIPE] run step[{self._idx}]: {step}")
            pool_merge(self.s, "pipeline", {"active": True, "idx": self._idx, "last_step": step, "ts": time.time()})

            ok, advance = self._run_step(step, snap)

            console.log(f"[PIPE] step result: ok={ok} advance={advance}")
            if ok and advance:
                self._idx += 1
                pool_merge(self.s, "pipeline", {"idx": self._idx})
                self._cd(0.5)
                console.log(f"[PIPE] advance -> idx={self._idx}")

            if self._idx >= len(order):
                self._finish()

        finally:
            self._running = False

    # ---------- steps ----------
    def _is_step_enabled(self, step: str) -> bool:
        feature = {
            "respawn":  "respawn",
            "buff":     "buff",
            "macros":   "macros",
            "teleport": "teleport",
            "record":   "record",
            "autofarm": "autofarm",
        }.get(step)
        if not feature:
            return True
        return bool(pool_get(self.s, f"features.{feature}.enabled", False))

    def _is_step_paused(self, step: str) -> bool:
        feature = {
            "respawn":  "respawn",
            "buff":     "buff",
            "macros":   "macros",
            "teleport": "teleport",
            "record":   "record",
            "autofarm": "autofarm",
        }.get(step)
        if not feature:
            return False
        return bool(pool_get(self.s, f"features.{feature}.paused", False))

    def _call_server_rule(self, engine: str, func: str = "run_step"):
        """По умолчанию ищем core.engines.{engine}.server.{server}.rules"""
        server = pool_get(self.s, "config.server", None)
        if not server:
            console.log(f"[PIPE] {engine}: server is not set in pool (config.server)")
            return None
        mod_name = f"core.engines.{engine}.server.{str(server).lower()}.rules"
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, func, None)
            if callable(fn):
                return fn
        except Exception as e:
            console.log(f"[PIPE] {engine}: import error for {mod_name}: {e}")
        return None

    def _call_dashboard_rule(self, submodule: str, func: str = "run_step"):
        """
        Вложенные правила dashboard: buffer/teleport/…:
        core.engines.dashboard.server.{server}.{submodule}.rules
        """
        server = pool_get(self.s, "config.server", None)
        if not server:
            console.log("[PIPE] dashboard: server is not set in pool (config.server)")
            return None
        mod_name = f"core.engines.dashboard.server.{str(server).lower()}.{submodule}.rules"
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, func, None)
            if callable(fn):
                return fn
        except Exception as e:
            console.log(f"[PIPE] dashboard: import error for {mod_name}: {e}")
        return None

    def _run_step(self, step: str, snap: Snapshot) -> tuple[bool, bool]:
        step = (step or "").lower().strip()

        # уважаем тумблер шага
        if not self._is_step_enabled(step):
            console.log(f"[PIPE] {step}: disabled -> pass")
            # disabled — считаем успешно «пройдено»
            return True, True

        # НОВОЕ: пауза шага — ждём (не продвигаем индекс!)
        if self._is_step_paused(step):
            console.log(f"[PIPE] {step}: paused -> wait")
            return False, False

        # busy для шагов, которыми управляем из оркестратора
        def _busy_on(feat): self._set_busy(feat, True)
        def _busy_off(feat): self._set_busy(feat, False)

        if step == "respawn":
            _busy_on("respawn")
            try:
                fn = self._call_server_rule("respawn")
                if callable(fn):
                    try:
                        ok, adv = fn(
                            state=self.s,
                            ps_adapter=self.ps,
                            controller=self.controller,
                            snap=snap,
                            helpers={
                                "respawn_runner": self._respawn_runner,
                                "get_window": lambda: pool_get(self.s, "window.info", None),
                                "get_language": lambda: pool_get(self.s, "config.language", "rus"),
                            },
                        )
                        return bool(ok), bool(adv)
                    except Exception as e:
                        console.log(f"[RESPAWN] rules error: {e}")
                        self._hud_err("[RESPAWN] ошибка server rules — пропуск шага")
                        return True, True
                self._hud_err("[RESPAWN] rules.py не найден для сервера — пропуск шага")
                return True, True
            finally:
                _busy_off("respawn")

        if step == "macros":
            _busy_on("macros")
            try:
                fn = self._call_server_rule("macros")
                if callable(fn):
                    try:
                        ok, adv = fn(
                            state=self.s,
                            ps_adapter=self.ps,
                            controller=self.controller,
                            snap=snap,
                            helpers={
                                "get_window": lambda: pool_get(self.s, "window.info", None),
                                "get_language": lambda: pool_get(self.s, "config.language", "rus"),
                            },
                        )
                        return bool(ok), bool(adv)
                    except Exception as e:
                        console.log(f"[MACROS] rules error: {e}")
                        self._hud_err("[MACROS] ошибка server rules — пропуск шага")
                        return True, True
                self._hud_err("[MACROS] rules.py не найден для сервера — пропуск шага")
                return True, True
            finally:
                _busy_off("macros")

        if step == "buff":
            _busy_on("buff")
            try:
                # dashboard → buffer.rules
                fn = self._call_dashboard_rule("buffer", func="run_step")
                if callable(fn):
                    try:
                        ok, adv = fn(
                            state=self.s,
                            ps_adapter=self.ps,
                            controller=self.controller,
                            snap=snap,
                            helpers={
                                "get_window": lambda: pool_get(self.s, "window.info", None),
                                "get_language": lambda: pool_get(self.s, "config.language", "rus"),
                            },
                        )
                        return bool(ok), bool(adv)
                    except Exception as e:
                        console.log(f"[BUFF] dashboard/buffer rules error: {e}")
                        self._hud_err("[BUFF] ошибка dashboard/buffer rules — пропуск шага")
                        return True, True
                console.log("[BUFF] dashboard/buffer rules.py не найден — пропуск шага")
                self._hud_err("[BUFF] dashboard/buffer rules.py не найден — пропуск шага")
                return True, True
            finally:
                _busy_off("buff")

        if step == "teleport":
            _busy_on("teleport")
            try:
                # если появится dashboard/teleport.rules — подцепится автоматически
                fn = self._call_dashboard_rule("teleport", func="run_step")
                if callable(fn):
                    try:
                        ok, adv = fn(
                            state=self.s,
                            ps_adapter=self.ps,
                            controller=self.controller,
                            snap=snap,
                            helpers={
                                "get_window": lambda: pool_get(self.s, "window.info", None),
                                "get_language": lambda: pool_get(self.s, "config.language", "rus"),
                            },
                        )
                        return bool(ok), bool(adv)
                    except Exception as e:
                        console.log(f"[Teleport] dashboard/teleport rules error: {e}")
                        self._hud_err("[Teleport] ошибка dashboard/teleport rules — пропуск шага")
                        return True, True
                # временный заглушечный успех
                self._hud_succ("[Teleport] выполнено (stub)")
                console.log("[Teleport] stub ok (rules not found)")
                return True, True
            finally:
                _busy_off("teleport")

        if step == "record":
            _busy_on("record")
            try:
                from core.engines.record import rules as rec_rules
                ok, adv = rec_rules.run_step(
                    state=self.s,
                    ps_adapter=self.ps,
                    controller=self.controller,
                    snap=snap,
                    helpers={**self._helpers, "state": self.s},
                )
                return bool(ok), bool(adv)
            except Exception as e:
                console.log(f"[RECORD] rules error: {e}")
                self._hud_err("[RECORD] ошибка rules — пропуск шага")
                return True, True
            finally:
                _busy_off("record")

        if step == "autofarm":
            # busy автофарма помечает сам сервис, т.к. это долговременный цикл
            fn = self._call_server_rule("autofarm")
            if callable(fn):
                try:
                    ok, adv = fn(
                        state=self.s,
                        ps_adapter=self.ps,
                        controller=self.controller,
                        snap=snap,
                        helpers={
                            "get_window": lambda: pool_get(self.s, "window.info", None),
                            "get_language": lambda: pool_get(self.s, "config.language", "rus"),
                        },
                    )
                    return bool(ok), bool(adv)
                except Exception as e:
                    console.log(f"[AUTOFARM] rules error: {e}")
                    self._hud_err("[AUTOFARM] ошибка server rules — пропуск шага")
                    return True, True
            self._hud_err("[AUTOFARM] rules.py не найден для сервера — пропуск шага")
            return True, True

        console.log(f"[PIPE] unknown step: {step}")
        self._hud_err(f"[PIPE] неизвестный шаг: {step} — пропуск")
        return True, True

    # ---------- utils ----------
    def _order(self) -> List[str]:
        raw = list(pool_get(self.s, "pipeline.order",
                            ["respawn", "buff", "teleport", "macros", "record", "autofarm"]) or [])
        if not raw:
            raw = ["respawn", "buff", "teleport", "macros", "record", "autofarm"]
        rest = [x for x in raw if x and x.lower() != "respawn"]
        return ["respawn"] + rest

    def _load_respawn_module(self, server: str):
        server = (server or "").strip().lower()
        if not server:
            raise RuntimeError("config.server is not set")
        module_name = f"core.engines.respawn.server.{server}.engine"
        return importlib.import_module(module_name)

    def _make_respawn_engine(self):
        server = pool_get(self.s, "config.server", None)
        if not server:
            raise RuntimeError("config.server is not set")
        mod = self._load_respawn_module(server)

        create_engine = getattr(mod, "create_engine", None)
        RespawnEngine = getattr(mod, "RespawnEngine", None)

        # общие параметры из пула
        click_threshold = float(pool_get(self.s, "features.respawn.click_threshold", 0.70))
        confirm_timeout_s = float(pool_get(self.s, "features.respawn.confirm_timeout_s", 6.0))

        def _is_alive():
            try:
                st = self.ps.last() or {}
                return bool(st.get("alive"))
            except Exception:
                return True

        if callable(create_engine):
            return create_engine(
                server=server,
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=click_threshold,
                confirm_timeout_s=confirm_timeout_s,
            )
        elif RespawnEngine is not None:
            return RespawnEngine(
                server=server,
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=click_threshold,
                confirm_timeout_s=confirm_timeout_s,
            )
        else:
            raise RuntimeError("Respawn engine class/factory not found in loaded module")

    def _finish(self):
        self._hud_ok("[PIPE] пайплайн завершён")
        console.log("[PIPE] finish: reset state")
        self._active = False
        self._idx = 0
        self._cd(1.0)
        pool_merge(self.s, "pipeline", {"active": False, "idx": 0, "ts": time.time()})


def make_pipeline_rule(state, ps_adapter, controller, helpers=None):
    return PipelineRule(state, ps_adapter, controller, helpers)
