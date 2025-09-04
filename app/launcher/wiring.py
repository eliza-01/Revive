# app/launcher/wiring.py
# единая точка, где создаются сервисы из core.* и прокидываются в секции.
from __future__ import annotations
from typing import Dict, Any
import json
import time

from core.connection import ReviveController
from core.runtime.state_watcher import StateWatcher
from core.features.flow_orchestrator import FlowOrchestrator
from core.features.restart_manager import RestartManager
from core.checks.charged import ChargeChecker, BuffTemplateProbe
from core.features.to_village import ToVillage
from core.servers.registry import get_server_profile, list_servers

from .sections.system import SystemSection
from .sections.state import StateSection
from .sections.respawn import RespawnSection
from .sections.buff import BuffSection
from .sections.macros import MacrosSection
from .sections.tp import TPSection
from .sections.autofarm import AutofarmSection

from core.orchestrators.runtime import orchestrator_tick
from core.engines.respawn.server.boh.orchestrator_rules import make_respawn_rule


def build_container(window, local_version: str, hud_window=None) -> Dict[str, Any]:
    # базовые зависимости
    controller = ReviveController()
    server = (list_servers() or ["l2mad"])[0]
    language = "rus"
    profile = get_server_profile(server)

    # планировщик
    import threading
    def schedule(fn, ms):
        t = threading.Timer(max(0.0, ms) / 1000.0, fn)
        t.daemon = True
        t.start()

    # shared state (минимум, остальное докинут секции по месту)
    sys_state: Dict[str, Any] = {
        "server": server,
        "language": language,
        "profile": profile,
        "window": None,
        "account": {"login": "", "password": "", "pin": ""},
        "buff_enabled": False,
        "_charged": None,

        # дефолты респавна (UI → SystemSection.get_init_state())
        "respawn_enabled": True,
        "respawn_wait_enabled": False,
        "respawn_wait_seconds": 120,
        "respawn_click_threshold": 0.70,
        "respawn_confirm_timeout_s": 6.0,
    }

    # --- HUD / лог в UI (должно быть ДО создания orch/rules) ---
    def hud_push(text: str):
        if not hud_window:
            return
        try:
            js = f"window.ReviveHUD && window.ReviveHUD.push({json.dumps(str(text))})"
            hud_window.evaluate_js(js)
        except Exception as e:
            print(f"[HUD] eval error: {e}")

    def log_ui(msg: str):
        try:
            print(msg)
        finally:
            hud_push(msg)

    # универсальный эмит в UI (аналог BaseSection.emit)
    def ui_emit(scope: str, text: str, ok):
        payload = {
            "scope": scope,
            "text": text,
            "ok": (True if ok is True else False if ok is False else None)
        }
        sys_state.setdefault("_last_status", {})[scope] = payload
        try:
            window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})")
        except Exception:
            pass

    sys_state["ui_emit"] = ui_emit

    # watcher + сервисы ядра
    watcher = StateWatcher(
        server=server,
        get_window=lambda: sys_state.get("window"),
        get_language=lambda: sys_state["language"],
        poll_interval=0.2,
        zero_hp_threshold=0.01,
        on_state=lambda st: None,            # секции подпишутся сами, если нужно
        on_dead=lambda st: orch.on_dead(st), # ссылка валидна во время вызова
        on_alive=lambda st: orch.on_alive(st),
        debug=True,
    )

    restart = RestartManager(
        controller=controller,
        get_server=lambda: sys_state["server"],
        get_window=lambda: sys_state.get("window"),
        get_language=lambda: sys_state["language"],
        watcher=watcher,
        account_getter=lambda: sys_state["account"],
        max_restart_attempts=3,
        retry_delay_s=1.0,
        logger=print,
    )

    to_village = ToVillage(
        controller=controller,
        server=server,
        get_window=lambda: sys_state.get("window"),
        get_language=lambda: sys_state["language"],
        click_threshold=0.87,
        debug=True,
        is_alive=lambda: watcher.is_alive(),
        confirm_timeout_s=3.0,
    )

    # оркестратор флоу (его лог уводим в HUD)
    orch = FlowOrchestrator(
        schedule=schedule,
        log=log_ui,
        checker=None,                # ChargeChecker ниже прицепим в sys_state (для секций)
        watcher=watcher,
        to_village=to_village,
        postrow_runner=None,         # секции добавят
        restart_manager=restart,
        get_server=lambda: sys_state["server"],
        get_language=lambda: sys_state["language"],
    )

    # ChargeChecker + проба «зарядки»
    checker = ChargeChecker(interval_minutes=10, mode="ANY")
    checker.register_probe(
        "autobuff_icons",
        BuffTemplateProbe(
            name="autobuff_icons",
            server_getter=lambda: sys_state["server"],
            get_window=lambda: sys_state.get("window"),
            get_language=lambda: sys_state["language"],
            zone_key="buff_bar",
            tpl_keys=["buff_icon_shield", "buff_icon_blessedBody"],
            threshold=0.85,
            debug=True,
        ),
        enabled=True,
    )
    sys_state["checker"] = checker

    # секции
    sections = [
        SystemSection(window, local_version, controller, watcher, orch, sys_state, schedule),
        StateSection(window, watcher, sys_state),         # мониторинг (watcher_* API)
        RespawnSection(window, sys_state),                # настройки респавна
        BuffSection(window, controller, watcher, sys_state, schedule, checker=checker),
        MacrosSection(window, controller, sys_state),
        TPSection(window, controller, watcher, sys_state, schedule),
        AutofarmSection(window, controller, watcher, sys_state, schedule),
    ]

    exposed: Dict[str, Any] = {}
    for sec in sections:
        try:
            exported = sec.expose()
            if isinstance(exported, dict):
                exposed.update(exported)
        except Exception as e:
            print(f"[wiring] expose() failed in {sec.__class__.__name__}: {e}")

    # === «Новый» оркестратор с правилом респавна ===
    rules = [make_respawn_rule(sys_state, watcher, controller)]

    _orch_stop = {"stop": False}
    sys_state["_orch_stop"] = _orch_stop

    def _orch_tick():
        if _orch_stop["stop"]:
            return
        try:
            orchestrator_tick(sys_state, watcher, rules)
        except Exception as e:
            print("[orch] tick error:", e)
        # ~5 тиков/сек
        schedule(_orch_tick, 200)

    # стартуем первый тик через 200 мс
    schedule(_orch_tick, 200)

    # exposed-хелпер для HUD (по необходимости)
    def hud_dump():
        try:
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}
    exposed["hud_dump"] = hud_dump

    _shutdown_done = False

    def shutdown():
        nonlocal _shutdown_done
        if _shutdown_done:
            return
        _shutdown_done = True

        # 1) остановить автоповторы/таймеры, которые сами себя перезапускают
        try:
            sys_state["_autofind_stop"] = True
            _orch_stop["stop"] = True
        except Exception as e:
            print(f"[shutdown] flags: {e}")

        # 2) гасим внешние сервисы (rows_ctrl, orch, checker — если есть)
        try:
            rc = sys_state.get("rows_ctrl")
            if rc and hasattr(rc, "stop"):
                rc.stop()
        except Exception as e:
            print(f"[shutdown] rows_ctrl.stop(): {e}")

        try:
            if orch and hasattr(orch, "shutdown"):
                orch.shutdown()
        except Exception as e:
            print(f"[shutdown] orch.shutdown(): {e}")

        try:
            chk = sys_state.get("checker")
            if chk and hasattr(chk, "stop"):
                chk.stop()
        except Exception as e:
            print(f"[shutdown] checker.stop(): {e}")

        # 3) останавливаем watcher и ЖДЁМ его завершения
        try:
            watcher.stop()
            for _ in range(20):  # ~2 сек максимум
                if not watcher.is_running():
                    break
                time.sleep(0.1)
        except Exception as e:
            print(f"[shutdown] watcher.stop(): {e}")

        # 4) закрываем контроллер (последним)
        try:
            if controller:
                controller.close()
        except Exception as e:
            print(f"[shutdown] controller.close(): {e}")

    return {"sections": sections, "shutdown": shutdown, "exposed": exposed}
