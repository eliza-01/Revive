# app/launcher/wiring.py
from __future__ import annotations
from typing import Dict, Any, Optional
import json

from core.arduino.connection import ReviveController
from core.config.servers import get_server_profile, list_servers

# секции
from .sections.system import SystemSection
from .sections.state import StateSection
from .sections.respawn import RespawnSection
from .sections.buff import BuffSection
from .sections.macros import MacrosSection
from .sections.tp import TPSection
from .sections.autofarm import AutofarmSection
from .sections.pipeline import PipelineSection

# оркестратор
from core.orchestrators.pipeline_rule import make_pipeline_rule

# движки/сервисы (правила)
from core.engines.window_focus.orchestrator_rules import make_focus_pause_rule

# пул
from core.state.pool import ensure_pool, pool_get, pool_write, dump_pool

# новые хелперы
from app.launcher.infra.ui_bridge import UIBridge
from app.launcher.infra.expose import expose_api
from app.launcher.infra.orchestrator_loop import OrchestratorLoop
from app.launcher.infra.services import ServicesBundle


import importlib
from core.engines.ui_guard.runner import UIGuardRunner

def build_container(window, local_version: str, hud_window=None) -> Dict[str, Any]:
    controller = ReviveController()
    servers = list_servers() or ["boh"]
    server = servers[0]
    language = "rus"
    profile = get_server_profile(server)

    # === state / pool ===
    state: Dict[str, Any] = {}
    ensure_pool(state)

    # базовая инициализация пула
    pool_write(state, "app", {"version": local_version})
    pool_write(state, "config", {"server": server, "language": language, "profile": profile, "profiles": servers})
    pool_write(state, "account", {"login": "", "password": "", "pin": ""})
    pool_write(state, "window", {"info": None, "found": False, "title": ""})
    pool_write(state, "services.window_focus", {"running": False})
    pool_write(state, "services.player_state", {"running": False})
    pool_write(state, "services.macros_repeat", {"running": False})

    # фичи/пайплайн дефолты
    pool_write(state, "features.respawn", {
        "enabled": False, "wait_enabled": False, "wait_seconds": 30,
        "click_threshold": 0.70, "confirm_timeout_s": 6.0, "status": "idle",
    })
    pool_write(state, "features.macros", {
        "enabled": False, "repeat_enabled": False, "rows": [],
        "run_always": False, "delay_s": 1.0, "duration_s": 2.0, "sequence": ["1"], "status": "idle",
    })
    pool_write(state, "features.buff", {"enabled": False, "mode": "", "methods": [], "status": "idle"})
    pool_write(state, "features.tp", {"enabled": False, "status": "idle"})
    pool_write(state, "features.autofarm", {"enabled": False, "status": "idle"})
    pool_write(state, "pipeline", {
        "allowed": ["respawn", "buff", "macros", "tp", "autofarm"],
        "order": ["respawn", "macros"],
        "active": False, "idx": 0, "last_step": ""
    })

    # === UI-мост ===
    ui = UIBridge(window, state, hud_window)

    # === Сервисы (вынесены) ===
    services = ServicesBundle(state, window, hud_window, ui, controller)
    ps_adapter = services.ps_adapter

    # # --- Включаем ui_guard по умолчанию ---
    # pool_write(state, "ui_guard", {"enabled": True, "tracker": "empty"})
    # # --- Инициализируем ui_guard runner + тикер 2 сек ---
    # def _make_ui_guard_engine():
    #     srv = (pool_get(state, "config.server", "boh") or "boh").lower()
    #     debug = bool(pool_get(state, "runtime.debug.pool_debug", False))
    #     mod = importlib.import_module(f"core.engines.ui_guard.server.{srv}.engine")
    #     create = getattr(mod, "create_engine", None)
    #     Engine = getattr(mod, "UIGuardEngine", None)
    #     if callable(create):
    #         return create(server=srv, controller=controller, debug=debug, on_report=ui.log)
    #     elif Engine is not None:
    #         return Engine(server=srv, controller=controller, debug=debug, on_report=ui.log)
    #     raise RuntimeError("UIGuard engine not found")
    #
    # ui_guard_runner = UIGuardRunner(
    #     engine=_make_ui_guard_engine(),
    #     get_window=lambda: pool_get(state, "window.info", None),
    #     get_language=lambda: pool_get(state, "config.language", "rus"),
    #     report=ui.log,
    #     is_focused=lambda: bool(pool_get(state, "focus.has_focus", False)),  # ← важно
    # )
    #
    # def _ui_guard_tick():
    #     try:
    #         if not pool_get(state, "ui_guard.enabled", True):
    #             return
    #         if not pool_get(state, "window.found", False):
    #             # ждём, пока SystemSection/find_window заполнит window.info
    #             return
    #
    #         res = ui_guard_runner.run_once()
    #
    #         # Обновляем трекер в пуле: нашли — пишем ключ, закрыли все — empty.
    #         if res.get("found"):
    #             key = str(res.get("key") or "")
    #             if key and key != "empty":
    #                 pool_write(state, "ui_guard", {"tracker": key})
    #             if res.get("closed"):
    #                 pool_write(state, "ui_guard", {"tracker": "empty"})
    #
    #     except Exception as e:
    #         ui.log(f"[UI_GUARD] error: {e}")
    #     finally:
    #         # Следующий запуск через ~2 сек от завершения текущего
    #         ui.schedule(_ui_guard_tick, 2000)
    # #
    # # стартуем первый тик сразу
    # _ui_guard_tick()


    # === Секции (UI API) ===
    sections = [
        SystemSection(window, local_version, controller, ps_adapter, state, ui.schedule),
        StateSection(window, services.ps_service, state),
        RespawnSection(window, state),
        BuffSection(window, controller, ps_adapter, state, ui.schedule, checker=None),
        MacrosSection(window, controller, state),
        TPSection(window, controller, ps_adapter, state, ui.schedule),
        AutofarmSection(window, controller, ps_adapter, state, ui.schedule),
        PipelineSection(window, state),
    ]

    exposed: Dict[str, Any] = {}
    for sec in sections:
        try:
            exported = sec.expose()
            if isinstance(exported, dict):
                exposed.update(exported)
        except Exception as e:
            print(f"[wiring] expose() failed in {sec.__class__.__name__}: {e}")

    # pool_dump для JS (pywebview.api.pool_dump)
    def pool_dump_api():
        try:
            return {"ok": True, "state": dump_pool(state, compact=True)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    exposed["pool_dump"] = pool_dump_api

    # отдать API в pywebview
    try:
        expose_api(window, exposed)
    except Exception as e:
        print("[wiring] expose error:", e)

    # === Правила оркестратора ===
    rules = [
        make_focus_pause_rule(state, {"grace_seconds": 0.3}),
        make_pipeline_rule(state, ps_adapter, controller, report=ui.log),
    ]
    loop = OrchestratorLoop(state, ps_adapter, rules, ui.schedule, period_ms=2222)

    # старт сервисов + оркестратора
    services.start()
    loop.start()

    def shutdown():
        try:
            loop.stop()
        except Exception:
            pass
        try:
            services.stop()
        except Exception:
            pass
        try:
            controller.close()
        except Exception as e:
            print(f"[shutdown] controller.close(): {e}")

    return {"sections": sections, "shutdown": shutdown, "exposed": exposed}
