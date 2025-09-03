# app/launcher/wiring.py
# единая точка, где создаются сервисы из core.* и прокидываются в секции.
from __future__ import annotations
from typing import Dict, Any
from core.connection import ReviveController
from core.runtime.state_watcher import StateWatcher
from core.features.flow_orchestrator import FlowOrchestrator
from core.features.restart_manager import RestartManager
from core.checks.charged import ChargeChecker, BuffTemplateProbe
from core.features.to_village import ToVillage
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
    def schedule(fn, ms):
        t = threading.Timer(max(0.0, ms) / 1000.0, fn)
        t.daemon = True
        t.start()

    # shared state (минимум, остальное докинут секции по месту)
    sys_state = {
        "server": server,
        "language": language,
        "profile": profile,
        "window": None,
        "account": {"login": "", "password": "", "pin": ""},
        "buff_enabled": False,
        "_charged": None,   # актуальное знание о «заряженности» (обновляет секция бафа)
    }

    # watcher + сервисы ядра
    watcher = StateWatcher(
        server=server,
        get_window=lambda: sys_state.get("window"),
        get_language=lambda: sys_state["language"],
        poll_interval=0.2,
        zero_hp_threshold=0.01,
        on_state=lambda st: None,            # секции подпишутся сами, если нужно
        on_dead=lambda st: orch.on_dead(st),
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

    orch = FlowOrchestrator(
        schedule=schedule,
        log=print,
        checker=None,                # при необходимости секция system прикрутит ChargeChecker/пробы
        watcher=watcher,
        to_village=to_village,
        postrow_runner=None,         # секции добавят
        restart_manager=restart,
        get_server=lambda: sys_state["server"],
        get_language=lambda: sys_state["language"],
    )

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

    # секции
    sections = [
        SystemSection(window, local_version, controller, watcher, orch, sys_state, schedule),
        RespawnSection(window, controller, watcher, orch, sys_state, schedule),
        BuffSection(window, controller, watcher, sys_state, schedule, checker=None),  # если нужен checker — подставишь
        MacrosSection(window, controller, sys_state),
        TPSection(window, controller, watcher, sys_state, schedule),
        AutofarmSection(window, controller, watcher, sys_state, schedule),
    ]
    exposed = {}
    for sec in sections:
        try:
            exported = sec.expose()
            if isinstance(exported, dict):
                # при конфликте имён берём последнее объявление (или замени на проверку, если хочешь жёстко падать)
                exposed.update(exported)
        except Exception as e:
            print(f"[wiring] expose() failed in {sec.__class__.__name__}: {e}")

    def shutdown():
        try:
            watcher.stop()
        except:
            pass
        try:
            controller.close()
        except:
            pass
        # если где-то используешь AutobuffService — не забудь его сюда добавить и вызвать stop()

    return {"sections": sections, "shutdown": shutdown, "exposed": exposed}
