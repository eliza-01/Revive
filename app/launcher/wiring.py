# app/launcher/wiring.py
from __future__ import annotations
from typing import Dict, Any
import threading

from core.arduino.connection import ReviveController

# новая конфигурация через manifest
from core.config.servers import (
    list_servers,
    get_languages,
    get_section_flags,
    get_buff_methods,
    get_buff_modes,
    get_teleport_methods,
    get_teleport_categories,
    get_teleport_locations,
)

# секции
from .sections.system import SystemSection
from .sections.state import StateSection
from .sections.respawn import RespawnSection
from .sections.buff import BuffSection
from .sections.macros import MacrosSection
from .sections.teleport import TeleportSection
from .sections.autofarm import AutofarmSection
from .sections.pipeline import PipelineSection
from .sections.record import RecordSection

# оркестратор
from core.orchestrators.pipeline_rule import make_pipeline_rule

# пул
from core.state.pool import ensure_pool, pool_get, pool_write, dump_pool

# новые хелперы
from app.launcher.infra.ui_bridge import UIBridge
from app.launcher.infra.expose import expose_api
from app.launcher.infra.orchestrator_loop import OrchestratorLoop
from app.launcher.infra.services import ServicesBundle

from app.launcher.prefs import load_prefs, save_prefs, resolve_initial_with_prefs

# новый логгер
from core.logging import console

try:
    from pynput import keyboard as _hk_keyboard
    from pynput import mouse as _hk_mouse
    _HK_AVAILABLE = True
except Exception as _e:
    _HK_AVAILABLE = False


def build_container(window, local_version: str, hud_window=None) -> Dict[str, Any]:
    controller = ReviveController()

    # === servers / langs from manifest ===
    servers = list_servers()
    if not servers:
        raise RuntimeError("No servers in manifest")

    # === state / pool ===
    state: Dict[str, Any] = {}
    ensure_pool(state)

    # версия приложения
    pool_write(state, "app", {"version": local_version})

    # === prefs: загрузить и разрешить в значения для пула
    prefs = load_prefs()
    resolved = resolve_initial_with_prefs(prefs)

    # config.* + ui.sections
    pool_write(state, "config", {
        "server":        resolved["config.server"],
        "language":      resolved["config.language"],
        "app_language":  resolved["config.app_language"],
        "profiles":      servers,
    })
    pool_write(state, "ui.sections", resolved["ui.sections"])

    # окна/сервисы — как было
    pool_write(state, "account", {"login": "", "password": "", "pin": ""})
    pool_write(state, "window", {"info": None, "found": False, "title": ""})
    pool_write(state, "services.window_focus", {"running": False})
    pool_write(state, "services.player_state", {"running": False})
    pool_write(state, "services.macros_repeat", {"running": False})
    pool_write(state, "services.autofarm", {"running": False})

    # --- pipeline (allowed + order + базовые флаги состояния)
    pool_write(state, "pipeline", {
        "allowed":     resolved["pipeline.allowed"],
        "order":       resolved["pipeline.order"],
        "active": False, "idx": 0, "last_step": "",
        "paused": False, "pause_reason": "", "ts": 0.0,
    })

    # --- features: respawn
    pool_write(state, "features.respawn", {
        "enabled":           bool(resolved.get("features.respawn.enabled", False)),
        "wait_enabled":      bool(resolved.get("features.respawn.wait_enabled", False)),
        "wait_seconds":      float(resolved.get("features.respawn.wait_seconds", 30)),
        "click_threshold":   0.70,
        "confirm_timeout_s": 6.0,
        "status": "idle",
    })

    # --- features: macros
    pool_write(state, "features.macros", {
        "enabled": bool(resolved.get("features.macros.enabled", False)),
        "repeat_enabled": bool(resolved.get("features.macros.repeat_enabled", False)),
        "rows": list(resolved.get("features.macros.rows", []) or []),
        "status": "idle",
    })

    # --- features: buff
    pool_write(state, "features.buff", {
        "enabled": bool(resolved.get("features.buff.enabled", False)),
        "method":  resolved.get("features.buff.method", ""),
        "mode":    resolved.get("features.buff.mode", ""),
        "methods": list(resolved.get("features.buff.methods", []) or []),
        "modes":   list(resolved.get("features.buff.modes", []) or []),
        "checker": list(resolved.get("features.buff.checker", []) or []),
        "status": "idle",
    })

    # --- features: teleport
    pool_write(state, "features.teleport", {
        "enabled":  bool(resolved.get("features.teleport.enabled", False)),
        "method":   resolved.get("features.teleport.method", ""),
        "methods":  list(resolved.get("features.teleport.methods", []) or []),
        "category": resolved.get("features.teleport.category", ""),
        "location": resolved.get("features.teleport.location", ""),
        "status": "idle",
    })

    # --- features: autofarm
    pool_write(state, "features.autofarm", {
        "enabled": bool(resolved.get("features.autofarm.enabled", False)),
        "modes": list(resolved.get("features.autofarm.modes", []) or []),
        "mode": resolved.get("features.autofarm.mode", ""),
        "config": dict(resolved.get("features.autofarm.config", {}) or {}),
        "status": "idle",
    })

    # --- features: record  (инициализация из prefs)
    pool_write(state, "features.record", {
        "enabled": bool(resolved.get("features.record.enabled", False)),
        "current_record": str(resolved.get("features.record.current_record", "")),
        "status": "idle",
    })

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
        TeleportSection(window, controller, ps_adapter, state, ui.schedule),
        AutofarmSection(window, controller, ps_adapter, state, ui.schedule),
        PipelineSection(window, state),
        RecordSection(state=state, controller=controller, get_window=lambda: pool_get(state, "window.info", None)),
    ]

    # запустить глобальные хуки записи
    rec_sec = next((s for s in sections if isinstance(s, RecordSection)), None)
    if rec_sec:
        try:
            rec_sec.start_global_hooks()
        except Exception as e:
            console.log(f"[wiring] record hooks start error: {e}")

    exposed: Dict[str, Any] = {}
    for sec in sections:
        try:
            exported = sec.expose()
            if isinstance(exported, dict):
                exposed.update(exported)
        except Exception as e:
            console.log(f"[wiring] expose() failed in {sec.__class__.__name__}: {e}")

    # Экспорт ui_guard_watch в API
    try:
        exposed["ui_guard_watch"] = services.ui_guard_watch
    except Exception:
        pass

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
    # Паузы раздаёт CoordinatorService, PS-правила выполняются собственным раннером.
    rules = [
        make_pipeline_rule(state, ps_adapter, controller, helpers={
            "record_engine": (rec_sec.runner.engine if rec_sec else None)
        }),
    ]

    loop = OrchestratorLoop(state, ps_adapter, rules, ui.schedule, period_ms=1500)

    # старт сервисов + оркестратора
    services.start()
    loop.start()

    console.hud("att", "Сервисы запущены ❤️")
    threading.Timer(5.0, console.hud_clear).start()

    def shutdown():
        try:
            loop.stop()
        except Exception:
            pass
        try:
            services.stop()
        except Exception:
            pass

        # Сохраняем prefs перед закрытием
        try:
            save_prefs(state)
        except Exception:
            pass

        # остановить хуки записи
        try:
            if rec_sec:
                rec_sec.stop_global_hooks()
        except Exception:
            pass

        try:
            controller.close()
        except Exception as e:
            console.log(f"[shutdown] controller.close(): {e}")

    return {"sections": sections, "shutdown": shutdown, "exposed": exposed}
