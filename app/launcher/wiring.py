# app/launcher/wiring.py
from __future__ import annotations
from typing import Dict, Any
import json, time

from core.arduino.connection import ReviveController
from core.servers.registry import get_server_profile, list_servers

# секции
from .sections.system import SystemSection
from .sections.state import StateSection
from .sections.respawn import RespawnSection
from .sections.buff import BuffSection
from .sections.macros import MacrosSection
from .sections.tp import TPSection
from .sections.autofarm import AutofarmSection

# оркестратор
from core.orchestrators.runtime import orchestrator_tick
from core.engines.respawn.server.boh.orchestrator_rules import make_respawn_rule
from core.engines.window_focus.orchestrator_rules import make_focus_pause_rule  # ← из window_focus

# движки
from core.engines.player_state.runner import run_player_state
from core.engines.window_focus.runner import run_window_focus

def build_container(window, local_version: str, hud_window=None) -> Dict[str, Any]:
    controller = ReviveController()
    server = (list_servers() or ["boh"])[0]
    language = "rus"
    profile = get_server_profile(server)

    import threading
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

    # --- HUD ---
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

    # универсальный emit в основной UI
    def ui_emit(scope: str, text: str, ok):
        payload = {"scope": scope, "text": text, "ok": (True if ok is True else False if ok is False else None)}
        sys_state.setdefault("_last_status", {})[scope] = payload
        try:
            window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})")
        except Exception:
            pass
    sys_state["ui_emit"] = ui_emit

    # === Player State service ===
    sys_state["_ps_last"] = {}   # {'alive': bool|None, 'hp_ratio': float|None, 'ts': float}
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
        try:
            if hp is not None:
                window.evaluate_js(
                    f"document.getElementById('hp').textContent = '{int(max(0, min(1.0, float(hp))) * 100)} %'")
        except Exception:
            pass

            # → HUD vitals
        try:
            if hud_window:
                h = "" if hp is None else str(int(max(0, min(1.0, float(hp))) * 100))
                cp = data.get("cp_ratio")
                c = "" if cp is None else str(int(max(0, min(1.0, float(cp))) * 100))
                hud_window.evaluate_js(
                    f"window.ReviveHUD && window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})"
                )
        except Exception as e:
            print(f"[HUD] hp set error: {e}")

    import threading as _th, time as _time

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
                        # если активна пауза по фокусу — не читаем состояние и не стартуем движок
                        if bool((sys_state.get("_focus_pause") or {}).get("active")):
                            _time.sleep(0.2)
                            continue

                        run_player_state(
                            server=sys_state.get("server") or "boh",
                            get_window=lambda: sys_state.get("window"),
                            on_status=log_ui,
                            on_update=_on_ps_update,
                            cfg={"poll_interval": poll_interval},
                            # прерываем также если включилась пауза фокуса
                            should_abort=lambda: ((not self._run) or bool((sys_state.get("_focus_pause") or {}).get("active"))),
                        )
                    except Exception:
                        pass
                    _time.sleep(0.05)
                sys_state["_ps_running"] = False

            self._thr = _th.Thread(target=loop, daemon=True)
            self._thr.start()

        def stop(self):
            self._run = False
            # сбросить показатели в основном UI
            try:
                window.evaluate_js("document.getElementById('hp').textContent = '--'")
            except Exception:
                pass
            # сбросить показатели в HUD
            try:
                if hud_window:
                    hud_window.evaluate_js("window.ReviveHUD && window.ReviveHUD.setHP('--','--')")
            except Exception as e:
                print(f"[HUD] hp reset error: {e}")

    ps_service = _PlayerStateService()
    # зарегистрируем сервисы для оркестратора (может быть использовано другими правилами)
    sys_state.setdefault("_services", {})["player_state"] = ps_service

    # адаптер для оркестратора
    class _PSAdapter:
        def last(self) -> Dict[str, Any]:
            return sys_state.get("_ps_last") or {}

        def is_alive(self) -> bool:
            st = self.last()
            a = st.get("alive")
            return bool(a) if a is not None else False

        def is_running(self) -> bool:
            return bool(sys_state.get("_ps_running", False))

    ps_adapter = _PSAdapter()

    # === Window focus service (изолированный) ===
    sys_state["_wf_last"] = {"has_focus": None, "ts": 0.0}
    sys_state["_wf_running"] = False

    def _on_wf_update(data: Dict[str, Any]):
        # сохраняем предыдущее значение, чтобы логировать только на изменения
        prev = sys_state.get("_wf_last") or {}
        prev_focus = prev.get("has_focus")

        try:
            has_focus = bool(data.get("has_focus"))
        except Exception:
            has_focus = False
        ts = float(data.get("ts") or 0.0)

        sys_state["_wf_last"] = {"has_focus": has_focus, "ts": ts}

        # в HUD и UI — только при смене состояния
        if prev_focus is None or prev_focus != has_focus:
            txt = f"Фокус окна: {'да' if has_focus else 'нет'}"
            log_ui(f"[FOCUS] {'ON' if has_focus else 'OFF'}")
            try:
                ui_emit("focus", txt, True if has_focus else None)
            except Exception:
                pass

    class _WindowFocusService:
        def __init__(self):
            self._run = False
            self._thr = None

        def is_running(self) -> bool:
            return bool(self._run)

        def start(self, poll_interval: float = 2.0):
            if self._run:
                return
            self._run = True
            sys_state["_wf_running"] = True

            def loop():
                while self._run:
                    try:
                        run_window_focus(
                            server="common",
                            get_window=lambda: sys_state.get("window"),
                            on_status=lambda *_: None,
                            on_update=_on_wf_update,
                            cfg={"poll_interval": poll_interval, "debug_focus": True},
                            should_abort=lambda: (not self._run),
                        )
                    except Exception:
                        pass
                    _time.sleep(0.05)
                sys_state["_wf_running"] = False

            self._thr = _th.Thread(target=loop, daemon=True)
            self._thr.start()

        def stop(self):
            self._run = False

    wf_service = _WindowFocusService()

    # Секции
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

    # Правила оркестратора: СНАЧАЛА фокус/пауза, затем респавн
    rules = [
        make_focus_pause_rule(sys_state, {"grace_seconds": 0.0}),
        make_respawn_rule(sys_state, ps_adapter, controller, report=log_ui),
    ]

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

    # стартуем сервисы
    ps_service.start(poll_interval=0.25)
    wf_service.start(poll_interval=2.0)
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
        try: wf_service.stop()
        except Exception as e: print(f"[shutdown] wf_service.stop(): {e}")
        try: controller.close()
        except Exception as e: print(f"[shutdown] controller.close(): {e}")

    # HUD прочее
    def hud_dump():
        try: return {"ok": True}
        except Exception as e: return {"error": str(e)}
    exposed["hud_dump"] = hud_dump

    return {"sections": sections, "shutdown": shutdown, "exposed": exposed}
