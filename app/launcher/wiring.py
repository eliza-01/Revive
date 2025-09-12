# app/launcher/wiring.py
from __future__ import annotations
from typing import Dict, Any
import importlib

from core.arduino.connection import ReviveController

# новая конфигурация через manifest
from core.config.servers import (
    list_servers,
    get_languages,
    get_section_flags,
    get_buff_methods,
    get_buff_modes,
    get_tp_methods,
)

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
from core.engines.window_focus.rules import make_focus_pause_rule

# пул
from core.state.pool import ensure_pool, pool_get, pool_write, dump_pool

# новые хелперы
from app.launcher.infra.ui_bridge import UIBridge
from app.launcher.infra.expose import expose_api
from app.launcher.infra.orchestrator_loop import OrchestratorLoop
from app.launcher.infra.services import ServicesBundle

# новый логгер
from core.logging import console


def build_container(window, local_version: str, hud_window=None) -> Dict[str, Any]:
    controller = ReviveController()

    # === servers / langs from manifest ===
    servers = list_servers()
    if not servers:
        raise RuntimeError("No servers in manifest")
    server = servers[0]

    # L2 UI language — первый из списка для сервера
    l2_langs = get_languages(server)
    if not l2_langs:  # <<< жёсткая проверка без фолбэков
        console.log(f"No languages in manifest for server '{server}'")
        raise RuntimeError(f"No languages in manifest for server '{server}'")
    l2_lang = l2_langs[0]

    # === state / pool ===
    state: Dict[str, Any] = {}
    ensure_pool(state)

    # базовая инициализация пула
    pool_write(state, "app", {"version": local_version})
    # profile больше не используем — только server + languages
    pool_write(state, "config", {
        "server": server,
        "language": l2_lang,      # язык интерфейса L2
        "app_language": l2_lang,   # <<< язык приложения/консоли/HUD (UIBridge требует)
        "profiles": servers       # доступные сервера
    })
    pool_write(state, "account", {"login": "", "password": "", "pin": ""})
    pool_write(state, "window", {"info": None, "found": False, "title": ""})
    pool_write(state, "services.window_focus", {"running": False})
    pool_write(state, "services.player_state", {"running": False})
    pool_write(state, "services.macros_repeat", {"running": False})
    pool_write(state, "services.autofarm", {"running": False})

    # фичи/пайплайн дефолты
    pool_write(state, "features.respawn", {
        "enabled": False, "wait_enabled": False, "wait_seconds": 30,
        "click_threshold": 0.70, "confirm_timeout_s": 6.0, "status": "idle",
    })
    pool_write(state, "features.macros", {
        "enabled": False, "repeat_enabled": False, "rows": [],
        "run_always": False, "delay_s": 1.0, "duration_s": 2.0, "sequence": ["1"], "status": "idle",
    })
    # buff/tp методы из манифеста
    buff_methods = get_buff_methods(server)
    buff_modes = get_buff_modes(server)
    tp_methods = get_tp_methods(server)

    pool_write(state, "features.buff", {
        "enabled": False,
        "mode": (buff_modes[0] if buff_modes else ""),
        "method": (buff_methods[0] if buff_methods else ""),  # ← добавили
        "methods": buff_methods,
        "modes": buff_modes,
        "status": "idle"
    })
    pool_write(state, "features.tp", {"enabled": False, "status": "idle", "methods": tp_methods})
    pool_write(state, "features.autofarm", {"enabled": False, "status": "idle"})
    # pool_write(state, "pipeline", {
    #     "allowed": ["respawn", "buff", "macros", "tp", "autofarm"],
    #     "order": ["respawn", "macros", "autofarm"],
    #     "active": False, "idx": 0, "last_step": ""
    # })

    # для UI: какие секции показывать для текущего сервера
    pool_write(state, "ui.sections", get_section_flags(server))

    # === UI-мост ===
    ui = UIBridge(window, state, hud_window)

    # === Сервисы (вынесены) ===
    services = ServicesBundle(state, window, hud_window, ui, controller)
    ps_adapter = services.ps_adapter

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
            console.log(f"[wiring] expose() failed in {sec.__class__.__name__}: {e}")

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
        console.log(f"[wiring] expose error: {e}")

    # === Правила оркестратора ===
    rules = [
        make_focus_pause_rule(state, {"grace_seconds": 0.3}),
        make_pipeline_rule(state, ps_adapter, controller),
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
            console.log(f"[shutdown] controller.close(): {e}")

    return {"sections": sections, "shutdown": shutdown, "exposed": exposed}
