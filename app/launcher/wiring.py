from __future__ import annotations
from typing import Dict, Any, Optional
import json, time, threading

from core.arduino.connection import ReviveController
from core.servers import get_server_profile, list_servers

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
from core.orchestrators.runtime import orchestrator_tick
from core.orchestrators.pipeline_rule import make_pipeline_rule

# движки/сервисы
from core.engines.window_focus.orchestrator_rules import make_focus_pause_rule
from core.engines.player_state.service import PlayerStateService
from core.engines.window_focus.service import WindowFocusService
from core.engines.macros.service import MacrosRepeatService

# пул
from core.state.pool import ensure_pool, pool_write, pool_get, dump_pool


def build_container(window, local_version: str, hud_window=None) -> Dict[str, Any]:
    controller = ReviveController()
    servers = list_servers() or ["boh"]
    server = servers[0]
    language = "rus"
    profile = get_server_profile(server)

    def schedule(fn, ms):
        t = threading.Timer(max(0.0, ms) / 1000.0, fn)
        t.daemon = True
        t.start()

    # === ЕДИНЫЙ state (никаких legacy полей) ===
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

    def log_ui_with_ok(msg: str, ok: Optional[bool] = None):
        try:
            print(f"[MACROS] {msg}")
        finally:
            hud_push(f"Повтор макроса: {msg}")

    # --- UI emit + запись в пул ---
    def ui_emit(scope: str, text: str, ok):
        payload = {"scope": scope, "text": text, "ok": (True if ok is True else False if ok is False else None)}
        pool_write(state, f"ui_status.{scope}", {"text": text, "ok": payload["ok"]})
        try:
            window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})")
        except Exception:
            pass
    state["ui_emit"] = ui_emit

    # === Player State service ===
    def _on_ps_update(data: Dict[str, Any]):
        hp = data.get("hp_ratio")
        # не трогаем vitals, если нет фокуса
        if pool_get(state, "focus.has_focus") is False:
            return

        alive = None if hp is None else bool(hp > 0.001)
        pool_write(state, "player", {"alive": alive, "hp_ratio": hp, "cp_ratio": data.get("cp_ratio")})

        # HUD vitals
        try:
            if hud_window and pool_get(state, "focus.has_focus"):
                h = "" if hp is None else str(int(max(0, min(1.0, float(hp))) * 100))
                cp = data.get("cp_ratio")
                c = "" if cp is None else str(int(max(0, min(1.0, float(cp))) * 100))
                hud_window.evaluate_js(f"window.ReviveHUD && window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})")
        except Exception as e:
            print(f"[HUD] hp set error: {e}")

    ps_service = PlayerStateService(
        server=lambda: pool_get(state, "config.server", "boh"),
        get_window=lambda: pool_get(state, "window.info", None),
        on_update=_on_ps_update,
        on_status=log_ui,
    )

    # адаптер для оркестратора — читает только из пула
    class _PSAdapter:
        def last(self) -> Dict[str, Any]:
            p = pool_get(state, "player", {}) or {}
            return {"alive": p.get("alive"), "hp_ratio": p.get("hp_ratio"), "cp_ratio": p.get("cp_ratio"), "ts": p.get("ts")}
        def is_alive(self) -> bool:
            a = pool_get(state, "player.alive", None)
            return bool(a) if a is not None else False
        def is_running(self) -> bool:
            return bool(pool_get(state, "services.player_state.running", False))
    ps_adapter = _PSAdapter()

    # === Window focus service ===
    def _on_wf_update(data: Dict[str, Any]):
        prev_focus = pool_get(state, "focus.has_focus", None)
        try:
            has_focus = bool(data.get("has_focus"))
        except Exception:
            has_focus = False

        pool_write(state, "focus", {"has_focus": has_focus})

        # OFF → сброс vitals
        if has_focus is False:
            pool_write(state, "player", {"alive": None, "hp_ratio": None, "cp_ratio": None})
            try:
                if hud_window:
                    hud_window.evaluate_js("window.ReviveHUD && window.ReviveHUD.setHP('--','')")
            except Exception:
                pass
        # ON после OFF → восстановить HUD из пула
        elif hud_window and prev_focus is not True:
            last = pool_get(state, "player", {}) or {}
            hp = last.get("hp_ratio"); cp = last.get("cp_ratio")
            h = "" if hp is None else str(int(max(0, min(1.0, float(h))) * 100))
            c = "" if cp is None else str(int(max(0, min(1.0, float(cp))) * 100))
            try:
                hud_window.evaluate_js(f"window.ReviveHUD && window.ReviveHUD.setHP({json.dumps(h)}, {json.dumps(c)})")
            except Exception:
                pass

        # статус в UI при смене
        if prev_focus is None or prev_focus != has_focus:
            txt = f"Фокус окна: {'да' if has_focus else 'нет'}"
            log_ui(f"[FOCUS] {'ON' if has_focus else 'OFF'}")
            ui_emit("focus", txt, True if has_focus else None)

    wf_service = WindowFocusService(
        get_window=lambda: pool_get(state, "window.info", None),
        on_update=_on_wf_update,
        on_status=None,
    )

    # Секции (UI API)
    sections = [
        SystemSection(window, local_version, controller, ps_adapter, state, schedule),
        StateSection(window, ps_service, state),
        RespawnSection(window, state),
        BuffSection(window, controller, ps_adapter, state, schedule, checker=None),
        MacrosSection(window, controller, state),
        TPSection(window, controller, ps_adapter, state, schedule),
        AutofarmSection(window, controller, ps_adapter, state, schedule),
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

    # ---- pool_dump: JSON-safe дамп пула ----
    def pool_dump():
        try:
            return {"ok": True, "state": dump_pool(state, compact=True)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    exposed["pool_dump"] = pool_dump  # <— КЛЮЧ: имя JS-метода будет pool_dump

    # немедленно экспонируем всё в pywebview (чтобы JS точно увидел)
    def _expose_dict(win, api: Dict[str, Any]):
        wrappers = []
        for name, fn in api.items():
            # оборачиваем, чтобы имя функции в JS было ровно как в ключе
            def make_wrap(_fn, _name):
                def _w(*a, **kw):
                    return _fn(*a, **kw)

                _w.__name__ = _name
                return _w

            wrappers.append(make_wrap(fn, name))
        try:
            win.expose(*wrappers)
        except Exception as e:
            print("[wiring] expose error:", e)

    _expose_dict(window, exposed)

    # Правила оркестратора
    rules = [
        make_focus_pause_rule(state, {"grace_seconds": 0.3}),
        make_pipeline_rule(state, ps_adapter, controller, report=log_ui),
    ]

    orch_stop = {"stop": False}

    def _orch_tick():
        if orch_stop["stop"]:
            return
        try:
            orchestrator_tick(state, ps_adapter, rules)
            if pool_get(state, "runtime.debug.pool_debug", False):
                summary = {
                    "app": {"v": pool_get(state, "app.version"), "srv": pool_get(state, "config.server"),
                            "lang": pool_get(state, "config.language")},
                    "window": {"found": pool_get(state, "window.found"), "title": pool_get(state, "window.title", "")},
                    "focus": pool_get(state, "focus.has_focus"),
                    "player": {"alive": pool_get(state, "player.alive"), "hp": pool_get(state, "player.hp_ratio")},
                    "services": {
                        "ps": pool_get(state, "services.player_state.running"),
                        "wf": pool_get(state, "services.window_focus.running"),
                        "mr": pool_get(state, "services.macros_repeat.running"),
                    },
                    "pipeline": {"order": pool_get(state, "pipeline.order"),
                                 "idx": pool_get(state, "pipeline.idx"),
                                 "active": pool_get(state, "pipeline.active")},
                }
                print("[POOL]", json.dumps(summary, ensure_ascii=False))
        except Exception as e:
            print("[orch] tick error:", e)
        schedule(_orch_tick, 2222)

    # старт сервисов
    wf_service.start(poll_interval=1.0)
    pool_write(state, "services.window_focus", {"running": True})

    ps_service.start(poll_interval=1.0)
    pool_write(state, "services.player_state", {"running": True})

    schedule(_orch_tick, 2222)

    # --- повторы макросов ---
    macros_repeat_service = MacrosRepeatService(
        server=lambda: pool_get(state, "config.server", "boh"),
        controller=controller,
        get_window=lambda: pool_get(state, "window.info", None),
        get_language=lambda: pool_get(state, "config.language", "rus"),
        get_rows=lambda: list(pool_get(state, "features.macros.rows", []) or []),
        is_enabled=lambda: bool(pool_get(state, "features.macros.repeat_enabled", False)),
        is_alive=lambda: bool(pool_get(state, "player.alive", False)),
        on_status=log_ui_with_ok,
    )
    macros_repeat_service.start(poll_interval=1.0)
    pool_write(state, "services.macros_repeat", {"running": True})

    def shutdown():
        try:
            orch_stop["stop"] = True
        except Exception:
            pass
        try:
            ps_service.stop()
        except Exception as e:
            print(f"[shutdown] ps_service.stop(): {e}")
        finally:
            pool_write(state, "services.player_state", {"running": False})
        try:
            wf_service.stop()
        except Exception as e:
            print(f"[shutdown] wf_service.stop(): {e}")
        finally:
            pool_write(state, "services.window_focus", {"running": False})
        try:
            controller.close()
        except Exception as e:
            print(f"[shutdown] controller.close(): {e}")
        try:
            macros_repeat_service.stop()
        except Exception as e:
            print(f"[shutdown] macros_repeat_service.stop(): {e}")
        finally:
            pool_write(state, "services.macros_repeat", {"running": False})

    return {"sections": sections, "shutdown": shutdown, "exposed": exposed}
