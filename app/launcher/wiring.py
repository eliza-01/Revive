# app/launcher/wiring.py
from __future__ import annotations
from typing import Dict, Any
import json, time, threading

from core.arduino.connection import ReviveController
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

from core.engines.player_state.runner import run_player_state

def build_container(window, local_version: str, hud_window=None) -> Dict[str, Any]:
    controller = ReviveController()
    server = (list_servers() or ["l2mad"])[0]
    language = "rus"
    profile = get_server_profile(server)

    def schedule(fn, ms):
        t = threading.Timer(max(0.0, ms) / 1000.0, fn)
        t.daemon = True
        t.start()

    sys_state: Dict[str, Any] = {
        "server": server,
        "language": language,
        "profile": profile,
        "window": None,
        "account": {"login": "", "password": "", "pin": ""},
        "_charged": None,

        # респавн дефолты
        "respawn_enabled": True,
        "respawn_wait_enabled": False,
        "respawn_wait_seconds": 120,
        "respawn_click_threshold": 0.70,
        "respawn_confirm_timeout_s": 6.0,
    }

    # --- HUD helpers ---
    def hud_push(text: str):
        if not hud_window:
            return
        try:
            js = f"window.ReviveHUD && window.ReviveHUD.push({json.dumps(str(text))})"
            hud_window.evaluate_js(js)
        except Exception as e:
            print(f"[HUD] eval error: {e}")

    def hud_set_hp(hp_percent: int, cp_percent: int = 100):
        if not hud_window:
            return
        try:
            js = f"window.ReviveHUD && window.ReviveHUD.setHP({int(hp_percent)}, {int(cp_percent)})"
            hud_window.evaluate_js(js)
        except Exception as e:
            print(f"[HUD] setHP error: {e}")

    def log_ui(msg: str):
        try:
            print(msg)
        finally:
            hud_push(msg)

    # универсальный emit в основной UI
    def ui_emit(scope: str, text: str, ok):
        payload = {"scope": scope, "text": text, "ok": (True if ok is True else False if ok is False else None)}
        sys_state.setdefault("_last_status", {})[scope] = payload
        try:
            window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})")
        except Exception:
            pass
    sys_state["ui_emit"] = ui_emit

    # === Player State (наш движок) ===
    sys_state["_ps_last"] = {}
    sys_state["_ps_running"] = False

    def _on_ps_update(data: Dict[str, Any]):
        hp = data.get("hp_ratio")
        alive = None if hp is None else bool(hp > 0.001)
        sys_state["_ps_last"] = {
            "alive": alive,
            "hp_ratio": hp,
            "cp_ratio": data.get("cp_ratio"),
            "ts": data.get("ts"),
        }
        # лёгкий апдейт в UI + HUD
        try:
            if hp is not None:
                pct = int(max(0, min(1.0, float(hp))) * 100)
                window.evaluate_js(f"const e=document.getElementById('hp'); if(e) e.textContent='{pct} %'")
                hud_set_hp(pct, 100)
        except Exception:
            pass

    class _PlayerStateService:
        def __init__(self):
            self._run = False
            self._thr = None

        def is_running(self) -> bool:
            return bool(self._run)

        def start(self, poll_interval: float = 0.25):
            if self._run:
                return
            self._run = True
            sys_state["_ps_running"] = True

            def loop():
                while self._run:
                    try:
                        run_player_state(
                            server=sys_state.get("server") or "boh",
                            get_window=lambda: sys_state.get("window"),
                            on_status=lambda *_: None,
                            on_update=_on_ps_update,
                            cfg={"poll_interval": poll_interval},
                            should_abort=lambda: (not self._run),
                        )
                    except Exception:
                        pass
                    time.sleep(0.05)
                sys_state["_ps_running"] = False

            self._thr = threading.Thread(target=loop, daemon=True)
            self._thr.start()

        def stop(self):
            self._run = False

    ps_service = _PlayerStateService()

    class _PSAdapter:
        def last(self) -> Dict[str, Any]:
            return sys_state.get("_ps_last") or {}

        def is_alive(self) -> bool:
            st = self.last()
            a = st.get("alive")
            return bool(a) if a is not None else False

        def is_running(self) -> bool:
            return bool(sys_state.get("_ps_running", False))

        # совместимость с SystemSection.set_server / set_language
        def set_server(self, *_): pass
        def set_language(self, *_): pass
        def stop(self): ps_service.stop()

    ps_adapter = _PSAdapter()

    sections = [
        SystemSection(window, local_version, controller, ps_adapter, sys_state, schedule),
        StateSection(window, ps_service, sys_state),
        RespawnSection(window, sys_state),
        BuffSection(window, controller, ps_adapter, sys_state, schedule, checker=None),
        MacrosSection(window, controller, sys_state),
        TPSection(window, controller, ps_adapter, sys_state, schedule),
        AutofarmSection(window, controller, ps_adapter, sys_state, schedule),
    ]

    exposed: Dict[str, Any] = {}
    for sec in sections:
        try:
            exported = sec.expose()
            if isinstance(exported, dict):
                exposed.update(exported)
        except Exception as e:
            print(f"[wiring] expose() failed in {sec.__class__.__name__}: {e}")

    rules = [make_respawn_rule(sys_state, ps_adapter, controller, report=log_ui)]

    _orch_stop = {"stop": False}
    sys_state["_orch_stop"] = _orch_stop

    def _orch_tick():
        if _orch_stop["stop"]:
            return
        try:
            orchestrator_tick(sys_state, ps_adapter, rules)
        except Exception as e:
            print("[orch] tick error:", e)
        schedule(_orch_tick, 200)

    ps_service.start(poll_interval=0.25)
    schedule(_orch_tick, 200)

    _shutdown_done = False
    def shutdown():
        nonlocal _shutdown_done
        if _shutdown_done: return
        _shutdown_done = True
        try: _orch_stop["stop"] = True
        except Exception: pass
        try: ps_service.stop()
        except Exception as e: print(f"[shutdown] ps_service.stop(): {e}")
        try: controller.close()
        except Exception as e: print(f"[shutdown] controller.close(): {e}")

    def hud_dump():
        try: return {"ok": True}
        except Exception as e: return {"error": str(e)}
    exposed["hud_dump"] = hud_dump

    return {"sections": sections, "shutdown": shutdown, "exposed": exposed}
