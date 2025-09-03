# app/launcher/wiring.py
# единая точка, где создаются сервисы из core.* и прокидываются в секции.
from __future__ import annotations
from typing import Dict, Any
from core.connection import ReviveController
from core.runtime.state_watcher import StateWatcher
from core.features.flow_orchestrator import FlowOrchestrator
from core.features.restart_manager import RestartManager
from core.features.to_village import ToVillage
from core.features.autobuff_service import AutobuffService
from core.servers.registry import get_server_profile, list_servers
from .sections.system import SystemSection
from .sections.respawn import RespawnSection
from .sections.buff import BuffSection
from .sections.macros import MacrosSection
from .sections.tp import TPSection
from .sections.autofarm import AutofarmSection

def build_container(window, local_version: str) -> Dict[str, Any]:
    # базовые зависимости
    controller = ReviveController()
    server = (list_servers() or ["l2mad"])[0]
    language = "rus"
    profile = get_server_profile(server)

    # планировщик
    import threading
    def schedule(fn, ms): t=threading.Timer(ms/1000.0, fn); t.daemon=True; t.start()

    # watcher + сервисы
    watcher = StateWatcher(
        server=server,
        get_window=lambda: sys_state.get("window"),
        get_language=lambda: sys_state["language"],
        poll_interval=0.2,
        zero_hp_threshold=0.01,
        on_state=lambda st: None,
        on_dead=lambda st: orch.on_dead(st),
        on_alive=lambda st: orch.on_alive(st),
        debug=True,
    )
    restart = RestartManager(controller=controller,
                             get_server=lambda: sys_state["server"],
                             get_window=lambda: sys_state.get("window"),
                             get_language=lambda: sys_state["language"],
                             watcher=watcher, account_getter=lambda: sys_state["account"],
                             max_restart_attempts=3, retry_delay_s=1.0, logger=print)

    to_village = ToVillage(controller=controller,
                           server=server,
                           get_window=lambda: sys_state.get("window"),
                           get_language=lambda: sys_state["language"],
                           click_threshold=0.87, debug=True,
                           is_alive=lambda: watcher.is_alive(), confirm_timeout_s=3.0)

    autobuff = AutobuffService(checker=None,  # подставишь свой ChargeChecker, если нужен
                               is_alive=lambda: watcher.is_alive(),
                               buff_is_enabled=lambda: sys_state["buff_enabled"],
                               buff_run_once=lambda: None,
                               on_charged_update=lambda v: sys_state.__setitem__("_charged", v),
                               tick_interval_s=1.0, log=print)

    orch = FlowOrchestrator(schedule=schedule, log=print, checker=None, watcher=watcher,
                            to_village=to_village, postrow_runner=None, restart_manager=restart,
                            get_server=lambda: sys_state["server"], get_language=lambda: sys_state["language"])

    # общее состояние (shared)
    sys_state = {
        "server": server,
        "language": language,
        "profile": profile,
        "window": None,
        "account": {"login": "", "password": "", "pin": ""},
        "buff_enabled": False,
        "_charged": None,
    }

    # секции
    sections = [
        SystemSection(window, local_version, controller, watcher, orch, sys_state, schedule),
        RespawnSection(window, controller, watcher, orch, sys_state, schedule),
        BuffSection(window, controller, watcher, sys_state, schedule),
        MacrosSection(window, controller, sys_state),
        TPSection(window, controller, watcher, sys_state, schedule),
        AutofarmSection(window, controller, watcher, sys_state, schedule),
    ]

    def shutdown():
        try: watcher.stop()
        except: pass
        try: autobuff.stop()
        except: pass
        try: controller.close()
        except: pass

    return {"sections": sections, "shutdown": shutdown}
