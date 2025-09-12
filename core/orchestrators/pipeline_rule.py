from __future__ import annotations
from typing import Any, Dict, List
import time
import importlib

from core.orchestrators.snapshot import Snapshot
from core.engines.respawn.runner import RespawnRunner

from core.state.pool import pool_get, pool_merge, pool_write
from core.logging import console


class PipelineRule:
    """
    Универсальный оркестратор-пайплайн.
    Следит за очередью шагов из пула (pipeline.order) и их завершением.
    Логику шагов (respawn/macros и др.) делегируем в server-специфичные rules.py.

    Репортов больше нет — сообщения уходим напрямую в HUD через console.hud.
    """

    def __init__(self, state: Dict[str, Any], ps_adapter, controller):
        self.s = state
        self.ps = ps_adapter
        self.controller = controller

        self._active = False
        self._idx = 0
        self._running = False
        self._busy_until = 0.0

        self._respawn_runner = RespawnRunner(
            engine=self._make_respawn_engine(),
            get_window=lambda: pool_get(self.s, "window.info", None),
            get_language=lambda: pool_get(self.s, "config.language", "rus"),
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

    # ---------- lifecycle ----------
    def when(self, snap: Snapshot) -> bool:
        now = time.time()
        if now < self._busy_until:
            console.log(f"[PIPE] skip: cooldown left {self._busy_until - now:.2f}s")
            return False
        if self._running:
            console.log("[PIPE] skip: already running")
            return False

        # --- ГЕЙТ ПО ФОКУСУ ---
        if snap.is_focused is False:
            console.log("[PIPE] skip: no focus — waiting focus=True to progress pipeline")
            console.log("skip pipeline: no focus")
            return False

        order = self._order()
        if not order:
            console.log("[PIPE] skip: empty order")
            return False

        # Корректный детект смерти
        is_dead = (snap.alive is False) or (snap.hp_ratio is not None and snap.hp_ratio <= 0.001)
        # Тумблер авто-респавна — только из пула
        respawn_on = bool(pool_get(self.s, "features.respawn.enabled", False))
        # Единственный _dbg — тик
        macros_on = bool(pool_get(self.s, "features.macros.enabled", False))
        self._dbg(
            "tick: "
            f"snap.is_focused={snap.is_focused} "
            f"snap.alive={snap.alive} snap.is_dead={is_dead} snap.hp={snap.hp_ratio} "
            f"respawn={respawn_on} macros={macros_on} active(pipeline?)={self._active} idx={self._idx}"
            f"----------------------------------------"
        )

        # Смерть есть, окно есть, а авто-респавн выключен — сообщим и подождём
        if (not self._active) and is_dead and (not respawn_on) and snap.has_window:
            console.log("[PIPE] no-activate: dead but respawn disabled")
            self._hud_err("[PIPE] смерть обнаружена, но авто-респавн выключен")
            self._busy_until = time.time() + 2.0
            return False

        # Активировать пайплайн
        if not self._active:
            if is_dead and respawn_on and snap.has_window:
                self._active = True
                self._idx = 0
                pool_merge(self.s, "pipeline", {"active": True, "idx": 0, "last_step": ""})
                console.log(f"[PIPE] activate: dead={is_dead} alive={snap.alive} hp={snap.hp_ratio}")
                self._hud_succ("[PIPE] старт пайплайна после смерти")
                return True
            return False

        # уже активен — двигаем шаг
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
            pool_merge(self.s, "pipeline", {"active": True, "idx": self._idx, "last_step": step})

            ok, advance = self._run_step(step, snap)

            console.log(f"[PIPE] step result: ok={ok} advance={advance}")
            if ok and advance:
                self._idx += 1
                pool_merge(self.s, "pipeline", {"idx": self._idx})
                self._busy_until = time.time() + 0.5
                console.log(f"[PIPE] advance -> idx={self._idx}")

            if self._idx >= len(order):
                self._finish()

        finally:
            self._running = False

    # ---------- steps ----------
    def _is_step_enabled(self, step: str) -> bool:
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

    def _call_server_rule(self, engine: str, func: str = "run_step"):
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

    def _run_step(self, step: str, snap: Snapshot) -> tuple[bool, bool]:
        step = (step or "").lower().strip()

        # уважаем тумблер шага
        if not self._is_step_enabled(step):
            console.log(f"[PIPE] {step}: disabled -> pass")
            return True, True

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
                return self._step_buff(snap)
            finally:
                _busy_off("buff")

        if step == "tp":
            _busy_on("tp")
            try:
                return self._step_tp(snap)
            finally:
                _busy_off("tp")

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

    # ---------- simple stubs (вынесем позже) ----------
    def _step_buff(self, snap: Snapshot) -> tuple[bool, bool]:
        self._hud_succ("[BUFF] выполнен (stub)")
        console.log("[BUFF] stub ok")
        return True, True

    def _step_tp(self, snap: Snapshot) -> tuple[bool, bool]:
        self._hud_succ("[TP] выполнено (stub)")
        console.log("[TP] stub ok")
        return True, True

    # ---------- utils ----------
    def _order(self) -> List[str]:
        raw = list(pool_get(self.s, "pipeline.order", ["respawn", "macros"]) or [])
        if not raw:
            raw = ["respawn", "macros"]
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
        debug = bool(pool_get(self.s, "runtime.debug.respawn_debug", False))

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
                debug=debug,
            )
        elif RespawnEngine is not None:
            return RespawnEngine(
                server=server,
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=click_threshold,
                confirm_timeout_s=confirm_timeout_s,
                debug=debug,
            )
        else:
            raise RuntimeError("Respawn engine class/factory not found in loaded module")

    def _finish(self):
        self._hud_ok("[PIPE] пайплайн завершён")
        console.log("[PIPE] finish: reset state")
        self._active = False
        self._idx = 0
        self._busy_until = time.time() + 1.0
        pool_merge(self.s, "pipeline", {"active": False, "idx": 0})


def make_pipeline_rule(state, ps_adapter, controller):
    return PipelineRule(state, ps_adapter, controller)
