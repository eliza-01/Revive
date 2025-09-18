# app/launcher/infra/services.py
from __future__ import annotations
from typing import Any, Dict, Optional
import json
import importlib
import time

from core.state.pool import pool_get, pool_write

# Сервисы домена
from core.engines.player_state.service import PlayerStateService
from core.engines.window_focus.service import WindowFocusService
from core.engines.macros.service import MacrosRepeatService
from core.engines.autofarm.service import AutoFarmService

# Координатор (управление флагами/паузами)
from core.engines.coordinator.engine import CoordinatorEngine
from core.engines.coordinator.service import CoordinatorService
from core.engines.coordinator.runner import CoordinatorRunner

# PS rules
from core.engines.player_state.rules_engine import PlayerStateRulesEngine
from core.engines.player_state.rules_runner import PlayerStateRulesRunner

# Прочее
from core.logging import console
from core.engines.ui_guard.runner import UIGuardRunner


# =========================
# Adapter
# =========================
class PSAdapter:
    """Лёгкий адаптер поверх пула для оркестратора/секций."""
    def __init__(self, state: Dict[str, Any]):
        self._state = state

    def last(self) -> Dict[str, Any]:
        p = pool_get(self._state, "player", {}) or {}
        return {
            "alive": p.get("alive"),
            "hp_ratio": p.get("hp_ratio"),
            "cp_ratio": p.get("cp_ratio"),
            "ts": p.get("ts"),
        }

    def is_alive(self) -> bool:
        a = pool_get(self._state, "player.alive", None)
        return bool(a) if a is not None else False

    def is_running(self) -> bool:
        return bool(pool_get(self._state, "services.player_state.running", False))


# =========================
# Services bundle
# =========================
class ServicesBundle:
    def __init__(self, state: Dict[str, Any], window, hud_window, ui, controller):
        self.state = state
        self.window = window
        self.hud_window = hud_window
        self.ui = ui
        self.controller = controller

        # ---------- 0) Адаптеры/утилиты ----------
        self.ps_adapter = PSAdapter(self.state)  # нужен рано

        def _status_map(ok: Optional[bool]) -> str:
            return "succ" if ok is True else "err" if ok is False else "ok"

        # (резерв на будущее)
        def _on_status(msg: str, ok: Optional[bool] = None):
            if ok is None:
                console.log(msg)
            else:
                console.log(f"{msg} [{'OK' if ok else 'FAIL'}]")
            console.hud(_status_map(ok), msg)

        def _on_status_macros(msg: str, ok: Optional[bool] = None):
            console.log(f"[MACROS] {msg}")
            console.hud(_status_map(ok), f"Повтор макроса: {msg}")

        # ---------- 1) UI GUARD интеграция (лениво) ----------
        self._ui_guard_runner: Optional[UIGuardRunner] = None  # создаём по требованию

        def _ensure_ui_guard_runner() -> Optional[UIGuardRunner]:
            if self._ui_guard_runner is not None:
                return self._ui_guard_runner
            try:
                srv = str(pool_get(self.state, "config.server", "") or "").lower()
                mod = importlib.import_module(f"core.engines.ui_guard.server.{srv}.engine")
                EngineCls = getattr(mod, "UIGuardEngine", None)
                if EngineCls is None:
                    console.log("[UI_GUARD] Engine class not found")
                    return None
                eng = EngineCls(server=srv, controller=self.controller, state=self.state)
                runner = UIGuardRunner(
                    engine=eng,
                    get_window=lambda: pool_get(self.state, "window.info", None),
                    get_language=lambda: pool_get(self.state, "config.language", "rus"),
                    # 👇 критично: прокинуть фокус из пула
                    is_focused=lambda: bool(pool_get(self.state, "focus.is_focused", True)),
                    state=self.state,
                )
                pool_write(self.state, "features.ui_guard", {"busy": False, "report": "empty"})
                self._ui_guard_runner = runner
                return runner
            except Exception as e:
                console.log(f"[UI_GUARD] init error: {e}")
                return None

        # делаем фабрику доступной вне __init__ (её будет использовать публичный метод)
        self._ensure_ui_guard_runner = _ensure_ui_guard_runner

        def _mask_hp_unknown_and_hud():
            """Пока экран перекрыт или UI-страж занят — HP/CP считаем неизвестными ('--')."""
            pool_write(self.state, "player", {"alive": None, "hp_ratio": None, "cp_ratio": None})
            try:
                if self.hud_window:
                    self.hud_window.evaluate_js("window.ReviveHUD && window.ReviveHUD.setHP('--','')")
            except Exception:
                pass

        def _hud(kind: str, text: str):
            try:
                console.hud(str(kind or "ok"), str(text or ""))
            except Exception:
                pass

        def _maybe_warn_overlay(report_val: str):
            """Сообщения в HUD при перекрытии индикатора HP."""
            if str(report_val or "").lower() == "empty":
                return
            af_busy = bool(pool_get(self.state, "features.autofarm.busy", False))
            tp_busy = bool(pool_get(self.state, "features.teleport.busy", False))
            bf_busy = bool(pool_get(self.state, "features.buff.busy", False))
            if af_busy:
                console.hud("att", "нужна отладка в этом месте")
            elif tp_busy or bf_busy:
                console.hud("att", "Вероятно, Alt B перекрыло индикатор HP")

        # ---------- 2) Player State service ----------
        def _on_ps_update(data: Dict[str, Any]):
            """
            ТОНКАЯ интеграция:
              - пауза PS -> маскируем виталы и HUD;
              - UI-guard busy/report -> маска + мягкое предупреждение;
              - иначе — пишем виталы и HUD.
            Запуск ui_guard по hp≈0 делаем в server-specific rules через PS rules runner.
            """
            # 0) Пауза сервиса — маска и выход
            if data.get("paused"):
                pool_write(self.state, "player", {"alive": None, "hp_ratio": None, "cp_ratio": None})
                try:
                    if self.hud_window and self.hud_window.evaluate_js(
                            "typeof window.ReviveHUD==='object' && typeof window.ReviveHUD.setHP==='function'"
                    ):
                        self.hud_window.evaluate_js("window.ReviveHUD.setHP('--','')")
                except Exception:
                    pass
                return

            hp = data.get("hp_ratio")
            cp = data.get("cp_ratio")

            # 0.5) Эвристика «жив» от фолбэка HP (мигающий низкий HP)
            if bool(data.get("fallback_alive", False)):
                pool_write(self.state, "player", {"alive": True, "hp_ratio": None, "cp_ratio": None})
                try:
                    if self.hud_window and self.hud_window.evaluate_js(
                            "typeof window.ReviveHUD==='object' && typeof window.ReviveHUD.setHP==='function'"
                    ):
                        self.hud_window.evaluate_js("window.ReviveHUD.setHP('--','')")
                except Exception:
                    pass
                try:
                    console.hud("att", "Индикатор HP чем-то перекрыт, но персонаж жив. Избегайте таких ситуаций")
                except Exception:
                    pass
                return

            # 0.6) Очистить HUD при возврате к основному движку
            if bool(data.get("fallback_clear_hud", False)):
                try:
                    console.hud_clear()
                except Exception:
                    pass

            # 1) Пока UI-guard занят или есть отчёт о перекрытии — виталы неизвестны
            ui_busy = bool(pool_get(self.state, "features.ui_guard.busy", False))
            ui_report = str(pool_get(self.state, "features.ui_guard.report", "empty") or "empty")
            if ui_busy or ui_report != "empty":
                _mask_hp_unknown_and_hud()
                _maybe_warn_overlay(ui_report)
                return

            # 2) Нормальная запись виталов и HUD
            try:
                hp_n = None if hp is None else max(0.0, min(1.0, float(hp)))
            except Exception:
                hp_n = None
            try:
                cp_n = None if cp is None else max(0.0, min(1.0, float(cp)))
            except Exception:
                cp_n = None

            if pool_get(self.state, "services.player_state.paused", False):
                return

            alive = None if hp_n is None else bool(hp_n > 0.001)
            pool_write(self.state, "player", {
                "alive": alive,
                "hp_ratio": hp_n,
                "cp_ratio": cp_n,
                "ts": data.get("ts"),
            })

            h = "" if hp_n is None else str(int(hp_n * 100))
            c = "" if cp_n is None else str(int(cp_n * 100))
            try:
                if self.hud_window and self.hud_window.evaluate_js(
                        "typeof window.ReviveHUD==='object' && typeof window.ReviveHUD.setHP==='function'"
                ):
                    self.hud_window.evaluate_js(
                        f"window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})"
                    )
            except Exception as e:
                console.log(f"[HUD] hp set error: {e}")

        self.ps_service = PlayerStateService(
            server=lambda: pool_get(self.state, "config.server", ""),
            get_window=lambda: pool_get(self.state, "window.info", None),
            on_update=_on_ps_update,
            is_paused=lambda: bool(pool_get(self.state, "services.player_state.paused", False)),
            get_pause_reason=lambda: str(pool_get(self.state, "services.player_state.pause_reason", "")),
        )

        # ---------- 3) Window Focus service ----------
        def _on_wf_update(data: Dict[str, Any]):
            prev = pool_get(self.state, "focus.is_focused", None)
            if "is_focused" not in data:
                return  # ничего не меняем, чтобы не сбивать таймер
            try:
                is_focused = bool(data.get("is_focused"))
            except Exception:
                is_focused = prev if prev is not None else False

            if prev is None or prev != is_focused:
                pool_write(self.state, "focus", {"is_focused": is_focused, "ts": time.time()})
            else:
                pool_write(self.state, "focus", {"is_focused": is_focused})

        self.wf_service = WindowFocusService(
            get_window=lambda: pool_get(self.state, "window.info", None),
            on_update=_on_wf_update,
        )

        # ---------- 4) Macros Repeat service ----------
        self.macros_repeat_service = MacrosRepeatService(
            server=lambda: pool_get(self.state, "config.server", ""),
            controller=self.controller,
            get_window=lambda: pool_get(self.state, "window.info", None),
            get_language=lambda: pool_get(self.state, "config.language", "rus"),
            get_rows=lambda: list(pool_get(self.state, "features.macros.rows", []) or []),
            is_enabled=lambda: bool(pool_get(self.state, "features.macros.repeat_enabled", False)),
            is_alive=lambda: pool_get(self.state, "player.alive", None),
            is_paused=lambda: bool(pool_get(self.state, "services.macros_repeat.paused", False)),
            set_busy=lambda b: pool_write(self.state, "features.macros", {"busy": bool(b)}),
        )

        # ---------- 5) AutoFarm service ----------
        self.autofarm_service = AutoFarmService(
            server=lambda: pool_get(self.state, "config.server", ""),
            controller=self.controller,
            get_window=lambda: pool_get(self.state, "window.info", None),
            get_language=lambda: pool_get(self.state, "config.language", "rus"),
            get_cfg=lambda: pool_get(self.state, "features.autofarm", {}),  # весь узел
            is_enabled=lambda: bool(pool_get(self.state, "features.autofarm.enabled", False)),
            is_alive=lambda: pool_get(self.state, "player.alive", None),
            is_paused=lambda: bool(pool_get(self.state, "services.autofarm.paused", False)),
            set_busy=lambda b: pool_write(self.state, "features.autofarm", {"busy": bool(b)}),
        )

        # ---------- 6) Регистрация сервисов в state["_services"] ----------
        try:
            self.state.setdefault("_services", {})
            self.state["_services"].update({
                "player_state": self.ps_service,
                "autofarm": self.autofarm_service,
                "macros_repeat": self.macros_repeat_service,
                # "window_focus": self.wf_service,  # при необходимости
            })
        except Exception:
            pass

        # ---------- 7) Coordinator service (после остальных) ----------
        cfg = CoordinatorEngine().build()  # универсальный билд
        # колбэки для автозапуска ui_guard из координатора (cor_2)
        def _ensure_ui_guard_watch_cb() -> bool:
            try:
                res = self.ui_guard_watch(True)
                return bool(res.get("ok", False))
            except Exception:
                return False

        def _ui_guard_is_busy_cb() -> bool:
            try:
                return bool(pool_get(self.state, "features.ui_guard.busy", False))
            except Exception:
                return False

        def _stop_ui_guard_watch_cb() -> bool:
            try:
                res = self.ui_guard_watch(False)
                return bool(res.get("ok", False))
            except Exception:
                return False

        self.coordinator_service = CoordinatorService(
            state=self.state,
            providers=cfg["providers"],
            reason_priority=cfg["reason_priority"],
            features=cfg["features"],
            services=cfg["services"],
            reason_scopes=cfg["reason_scopes"],
            period_ms=cfg["period_ms"],
            ensure_ui_guard_watch=_ensure_ui_guard_watch_cb,
            ui_guard_is_busy=_ui_guard_is_busy_cb,
            stop_ui_guard_watch=_stop_ui_guard_watch_cb,
        )
        self.coordinator_runner = CoordinatorRunner(self.state, self.coordinator_service)

        # Узел статуса координатора
        pool_write(self.state, "services.coordinator", {"running": False, "paused": False, "pause_reason": ""})

        # ---------- 8) PlayerState rules: engine + runner ----------
        self.ps_rules_engine = PlayerStateRulesEngine(
            state=self.state,
            get_server=lambda: pool_get(self.state, "config.server", "common"),
            ensure_ui_guard_runner=_ensure_ui_guard_runner,
            mask_vitals=_mask_hp_unknown_and_hud,
            hud=_hud,
        )
        self.ps_rules_runner = PlayerStateRulesRunner(self.ps_rules_engine, period_ms=250)
        pool_write(self.state, "services.player_state_rules", {"running": False})

        try:
            self.state["_services"].update({
                "coordinator": self.coordinator_service,
                "coordinator_runner": self.coordinator_runner,
                "player_state_rules": self.ps_rules_runner,
            })
        except Exception:
            pass

    # ---------- 8.5) UI Guard: публичный watch API ----------
    def ui_guard_watch(self, enable: bool = True, poll_ms: int = 500):
        # берём уже созданный или лениво создаём
        runner = self._ui_guard_runner or None
        if runner is None:
            try:
                runner = self._ensure_ui_guard_runner()
            except Exception:
                runner = None

        if runner is None:
            return {"ok": False, "watching": False, "error": "ui_guard runner not available"}

        try:
            if enable:
                if hasattr(runner, "start_watch"):
                    runner.start_watch(poll_ms=int(poll_ms))
                    pool_write(self.state, "features.ui_guard", {"watching": True})
                    return {"ok": True, "watching": True}
                return {"ok": False, "watching": False, "error": "start_watch() missing"}
            else:
                if hasattr(runner, "stop_watch"):
                    runner.stop_watch()
                pool_write(self.state, "features.ui_guard", {"watching": False})
                return {"ok": True, "watching": False}
        except Exception as e:
            return {"ok": False, "watching": False, "error": str(e)}

    # =========================
    # Lifecycle
    # =========================
    def start(self):
        # порядок старта: фокус -> PS -> фоновые -> координатор -> PS rules
        self.wf_service.start(poll_interval=1.0)
        pool_write(self.state, "services.window_focus", {"running": True})

        self.ps_service.start(poll_interval=1.0)
        pool_write(self.state, "services.player_state", {"running": True})

        self.macros_repeat_service.start(poll_interval=1.0)
        pool_write(self.state, "services.macros_repeat", {"running": True})

        self.autofarm_service.start(poll_interval=1.0)
        pool_write(self.state, "services.autofarm", {"running": True})

        self.coordinator_service.start()
        pool_write(self.state, "services.coordinator", {"running": True})

        self.ps_rules_runner.start()
        pool_write(self.state, "services.player_state_rules", {"running": True})

    def stop(self):
        # останавливаем в обратном порядке
        try:
            self.ps_rules_runner.stop()
        except Exception as e:
            console.log(f"[shutdown] ps_rules_runner.stop(): {e}")
        finally:
            pool_write(self.state, "services.player_state_rules", {"running": False})

        try:
            self.coordinator_service.stop()
        except Exception as e:
            console.log(f"[shutdown] coordinator_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.coordinator", {"running": False})

        try:
            self.autofarm_service.stop()
        except Exception as e:
            console.log(f"[shutdown] autofarm_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.autofarm", {"running": False})

        try:
            self.macros_repeat_service.stop()
        except Exception as e:
            console.log(f"[shutdown] macros_repeat_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.macros_repeat", {"running": False})

        try:
            self.ps_service.stop()
        except Exception as e:
            console.log(f"[shutdown] ps_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.player_state", {"running": False})

        try:
            self.wf_service.stop()
        except Exception as e:
            console.log(f"[shutdown] wf_service.stop(): {e}")
        finally:
            pool_write(self.state, "services.window_focus", {"running": False})
