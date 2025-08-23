# app/launcher_html.py
from __future__ import annotations
import os, importlib, threading, time
import webview

from core.connection import ReviveController
from core.connection_test import run_test_command
from core.servers.registry import list_servers, get_server_profile

# runtime/orchestrator stack (как в старом UI)
from core.runtime.state_watcher import StateWatcher
from core.checks.charged import ChargeChecker, BuffTemplateProbe
from core.features.afterbuff_macros import AfterBuffMacroRunner
from core.features.post_tp_row import PostTPRowRunner
from core.features.to_village import ToVillage
from core.features.flow_orchestrator import FlowOrchestrator
from core.features.restart_manager import RestartManager

# ТП-воркер (как в старом стеке)
from core.features.tp_after_respawn import TPAfterDeathWorker, TP_METHOD_DASHBOARD
from core.features.buff_after_respawn import BuffAfterRespawnWorker, BUFF_MODE_PROFILE

# gdi helpers
from core.vision.capture.gdi import find_window, get_window_info


def _safe_import(modpath: str):
    try:
        return importlib.import_module(modpath)
    except Exception:
        return None


class Repeater:
    def __init__(self, fn, interval_s: float):
        self.fn = fn; self.interval = max(0.05, float(interval_s))
        self._stop = threading.Event(); self._thr = None
    def start(self):
        if self._thr and self._thr.is_alive(): return
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, daemon=True); self._thr.start()
    def stop(self): self._stop.set()
    def _loop(self):
        while not self._stop.is_set():
            try: self.fn()
            except Exception: pass
            self._stop.wait(self.interval)


class _CheckerShim:
    """Фасад для оркестратора: всегда форсит проверку (как в старом UI)."""
    def __init__(self, checker: ChargeChecker):
        self.c = checker
    def is_charged(self, *_):
        try:
            return self.c.force_check()
        except Exception:
            return None
    def force_check(self, *_):
        try:
            return self.c.force_check()
        except Exception:
            return None
    def invalidate(self):
        try:
            self.c.invalidate()
        except Exception:
            pass


class Bridge:
    def __init__(self, version: str):
        self.version = version

        # ---- состояние / конфиг
        self.server_list = list_servers() or ["l2mad"]
        self.server = self.server_list[0]
        self.profile = get_server_profile(self.server)
        self.language = "rus"

        # ---- железо
        self.controller = ReviveController()

        # ---- окно
        self._window_info = None

        # ---- watcher (как раньше)
        self._last_state = None
        self.watcher = StateWatcher(
            server=self.server,
            get_window=lambda: self._window_info,
            get_language=lambda: self.language,
            poll_interval=0.2,
            zero_hp_threshold=0.01,
            on_state=lambda st: setattr(self, "_last_state", st),
            on_dead=self._on_dead_proxy,
            on_alive=self._on_alive_proxy,
            debug=False,
        )

        # ---- charged checker (как раньше)
        self.checker = ChargeChecker(interval_minutes=10, mode="ANY")
        self.checker.register_probe(
            "autobuff_icons",
            BuffTemplateProbe(
                name="autobuff_icons",
                server_getter=lambda: self.server,
                get_window=lambda: self._window_info,
                get_language=lambda: self.language,
                zone_key="buff_bar",
                tpl_keys=["buff_icon_shield", "buff_icon_blessedBody"],
                threshold=0.85,
                debug=False,
            ),
            enabled=True,
        )
        # фоновый тикер (не критичен, но полезен)
        self._checker_tick = Repeater(lambda: self.checker.tick(), 1.0)
        self._checker_tick.start()

        # ---- workers
        self.postrow = PostTPRowRunner(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._window_info,
            get_language=lambda: self.language,
            on_status=lambda msg, ok=None: print(msg),
        )
        self.to_village = ToVillage(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._window_info,
            get_language=lambda: self.language,
            click_threshold=0.87,
            debug=False,
            is_alive=lambda: self.watcher.is_alive(),
            confirm_timeout_s=3.0,
        )
        self.tp_worker = TPAfterDeathWorker(
            controller=self.controller,
            window_info=self._window_info,
            get_language=lambda: self.language,
            on_status=lambda msg, ok=None: print(msg),
            check_is_dead=lambda: not self.watcher.is_alive(),
            wait_alive_timeout_s=0.5,
            server=self.server,
        )

        # ---- рестарт + оркестратор
        self.restart = RestartManager(
            controller=self.controller,
            get_server=lambda: self.server,
            get_window=lambda: self._window_info,
            get_language=lambda: self.language,
            watcher=self.watcher,
            account_getter=lambda: getattr(self, "account", {"login": "", "password": "", "pin": ""}),
            max_restart_attempts=3,
            retry_delay_s=1.0,
            logger=print,
        )

        # простой планировщик "как root.after"
        def schedule(fn, ms): threading.Timer(max(0, ms) / 1000.0, fn).start()

        self.orch = FlowOrchestrator(
            schedule=schedule,
            log=print,
            checker=_CheckerShim(self.checker),   # ← форс-проверка charged
            watcher=self.watcher,
            to_village=self.to_village,
            postrow_runner=self.postrow,
            restart_manager=self.restart,
            get_server=lambda: self.server,
            get_language=lambda: self.language,
        )

        # ---- UI-переключатели (аналог виджетов)
        self._buff_enabled = False
        self._buff_mode = BUFF_MODE_PROFILE
        self._buff_method = getattr(self.profile, "get_buff_mode", lambda: "dashboard")()

        self._macros_enabled = False
        self._macros_run_always = False
        self._macros_seq = ["1"]
        self._macros_delay_s = 1.0
        self._macros_duration_s = 2.0
        self._macros_runner = AfterBuffMacroRunner(
            controller=self.controller,
            get_sequence=lambda: self._macros_seq,
            get_delay_s=lambda: self._macros_delay_s,
        )

        self._tp_cfg = {"cat": "", "loc": "", "method": TP_METHOD_DASHBOARD}
        self._selected_row_id = ""

        # ---- передаём «виджеты» в оркестратор (как в старом UI)
        self.orch.set_ui(
            buff_is_enabled=lambda: self._buff_enabled,
            buff_run_once=lambda: self._buff_run_once(),
            macros_ui_is_enabled=lambda: self._macros_enabled,
            macros_ui_run_always=lambda: self._macros_run_always,
            macros_ui_get_duration_s=lambda: self._macros_duration_s,
            macros_run_once=lambda: self._macros_runner.run_once(),
            # ВАЖНО: ТП считается включённым, если указаны cat и loc
            tp_is_enabled=lambda: bool(self._tp_cfg["cat"] and self._tp_cfg["loc"]),
            tp_teleport_now_selected=lambda: self._tp_teleport_now_selected(),
            tp_get_selected_destination=lambda: (self._tp_cfg["cat"], self._tp_cfg["loc"]),
            tp_get_selected_row_id=lambda: self._selected_row_id,
            respawn_ui_is_enabled=lambda: True,
        )

    # ── прокси watcher → orchestrator
    def _on_dead_proxy(self, st): self.orch.on_dead(st)
    def _on_alive_proxy(self, st): self.orch.on_alive(st)

    # ── системное
    def app_version(self): return {"version": self.version}
    def quit(self):
        try: self._checker_tick.stop()
        except Exception: pass
        try: self.watcher.stop()
        except Exception: pass
        try: self.controller.close()
        except Exception: pass
        os._exit(0)

    # ── сервер / язык
    def list_servers(self): return {"items": self.server_list}

    def set_server(self, server: str):
        self.server = (server or "l2mad").lower()
        self.profile = get_server_profile(self.server)
        try: self.watcher.set_server(self.server)
        except Exception: pass
        try: self.to_village.set_server(self.server)
        except Exception: pass
        try: self.postrow.set_server(self.server)
        except Exception: pass
        try:
            if hasattr(self.tp_worker, "set_server"):
                self.tp_worker.set_server(self.server)
            else:
                setattr(self.tp_worker, "server", self.server)
        except Exception: pass
        # дефолтный метод бафа из профиля
        try:
            cur = getattr(self.profile, "get_buff_mode", lambda: "")()
            if cur: self._buff_method = cur
        except Exception: pass
        return {"ok": True, "server": self.server}

    def get_server(self): return {"server": self.server}
    def set_language(self, lang: str):
        self.language = (lang or "rus").lower()
        return {"ok": True, "language": self.language}

    # ── окно клиента
    def find_window_now(self, titles: list[str] | None = None):
        titles = titles or ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
        found = False
        for t in titles:
            try:
                hwnd = find_window(t)
                if hwnd:
                    info = get_window_info(hwnd, client=True)
                    if all(k in info for k in ("x","y","width","height")):
                        self._window_info = info
                        try: self.tp_worker.window_info = info
                        except Exception: pass
                        found = True
                        break
            except Exception:
                pass
        return {"found": found, "window": (self._window_info or None)}

    def get_window(self):
        titles = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
        for t in titles:
            hwnd = find_window(t)
            if hwnd:
                info = get_window_info(hwnd, client=True)
                if all(k in info for k in ("x","y","width","height")):
                    self._window_info = info
                    try: self.tp_worker.window_info = info
                    except Exception: pass
                    try:
                        if not self.watcher.is_running():
                            self.watcher.start()
                    except Exception: pass
                    return {"found": True, "title": t, "window": info, "info": info}
        return {"found": False}

    # ── связь
    def ping_arduino(self):
        try:
            self.controller.send("ping")
            r = self.controller.read()
            return {"ok": r == "pong", "resp": r}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def test_connection(self):
        ok = run_test_command(self.controller, None)
        return {"ok": bool(ok)}

    # ── watcher / состояние
    def watcher_start(self):
        self.watcher.start(); return {"ok": True}
    def watcher_stop(self):
        self.watcher.stop();  return {"ok": True}
    def watcher_status(self):
        try: return {"running": bool(self.watcher.is_running())}
        except Exception: return {"running": False}

    def state_last(self):
        st = self._last_state
        if not st: return {"hp_ratio": None, "is_alive": None}
        hp = float(getattr(st, "hp_ratio", 0.0) or 0.0)
        return {"hp_ratio": hp, "is_alive": bool(hp > 0.01)}

    def is_alive(self): return {"alive": self.watcher.is_alive()}

    # ── charged
    def checker_enable(self, enable: bool):
        self.checker.set_enabled(bool(enable)); return {"ok": True}
    def charged_now(self): return {"charged": self.checker.force_check()}

    # ── аккаунт
    def account_get(self):
        return {"account": getattr(self, "account", {"login":"", "password":"", "pin":""})}
    def account_set(self, login: str, password: str, pin: str):
        self.account = {"login": login or "", "password": password or "", "pin": pin or ""}
        return {"ok": True}

    # ── баф (как в старом UI)
    def buff_supported_methods(self):
        try:
            methods = list(getattr(self.profile, "buff_supported_methods", lambda: [])())
            cur = getattr(self.profile, "get_buff_mode", lambda: "")()
            return {"methods": methods, "current": (cur or (methods[0] if methods else ""))}
        except Exception:
            return {"methods": ["dashboard"], "current": "dashboard"}

    def buff_set_mode(self, mode: str):
        self._buff_mode = (mode or BUFF_MODE_PROFILE).lower(); return {"ok": True}

    def buff_set_method(self, method: str):
        self._buff_method = (method or "dashboard").lower()
        try:
            if hasattr(self.profile, "set_buff_mode"):
                self.profile.set_buff_mode(self._buff_method)
        except Exception: pass
        return {"ok": True}

    def buff_enable(self, enable: bool):
        self._buff_enabled = bool(enable); return {"ok": True, "enabled": self._buff_enabled}

    def _wait_for_charged(self, timeout_s: float = 12.0, poll_s: float = 0.5) -> bool:
        """После бафа активно ждём появления иконок."""
        try: self.checker.invalidate()
        except Exception: pass
        t0 = time.time(); val = None
        while time.time() - t0 < timeout_s:
            try: val = self.checker.force_check()
            except Exception: val = None
            if val is True: return True
            time.sleep(poll_s)
        return bool(val)

    def _buff_run_once(self) -> bool:
        worker = BuffAfterRespawnWorker(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._window_info,
            get_language=lambda: self.language,
            on_status=lambda m, ok=None: print(m),
            click_threshold=0.87,
            debug=False,
        )
        worker.set_mode(self._buff_mode)
        try: worker.set_method(self._buff_method)
        except Exception: pass
        ok = bool(worker.run_once())
        if ok:
            self._wait_for_charged(timeout_s=8.0, poll_s=0.4)
        return ok

    def buff_run_once(self):
        ok = self._buff_run_once()
        try: charged = self.checker.force_check()
        except Exception: charged = None
        return {"ok": ok, "charged": charged}

    # ── макросы (как в старом UI)
    def macros_config(self, enabled: bool, seq: list[str], delay_s: float, duration_s: float, run_always: bool):
        self._macros_enabled = bool(enabled)
        self._macros_seq = list(seq or ["1"])
        self._macros_delay_s = max(0.0, float(delay_s or 0.0))
        self._macros_duration_s = max(0.0, float(duration_s or 0.0))
        self._macros_run_always = bool(run_always)
        return {"ok": True}

    def macros_run_once(self):
        return {"ok": self._macros_runner.run_once()}

    # ── ТП (как TPControls → teleport_now_selected)
    def tp_configure(self, category_id: str, location_id: str, method: str):
        self._tp_cfg = {"cat": category_id or "", "loc": location_id or "", "method": (method or TP_METHOD_DASHBOARD)}
        try:
            self.tp_worker.set_method(self._tp_cfg["method"])
            self.tp_worker.configure(self._tp_cfg["cat"], self._tp_cfg["loc"], self._tp_cfg["method"])
        except Exception: pass
        # ВАЖНО: включён, если цель задана (как в старом UI)
        enabled = bool(self._tp_cfg["cat"] and self._tp_cfg["loc"])
        return {"ok": True, **self._tp_cfg, "enabled": enabled}

    def _tp_teleport_now_selected(self) -> bool:
        if not (self._tp_cfg["cat"] and self._tp_cfg["loc"]):
            return False
        try: self.tp_worker.window_info = self._window_info
        except Exception: pass
        return bool(self.tp_worker.teleport_now(self._tp_cfg["cat"], self._tp_cfg["loc"], self._tp_cfg["method"]))

    def tp_now(self):
        return {"ok": self._tp_teleport_now_selected()}

    # ── rows (опционально)
    def rows_list(self, village_id: str, location_id: str):
        mod = _safe_import(f"core.servers.{self.server}.flows.rows.registry")
        if not mod or not hasattr(mod, "list_rows"): return {"items": []}
        rows = mod.list_rows(village_id, location_id) or []
        lang = self.language
        def title_of(r):
            if lang == "rus": return r.get("title_rus") or r.get("id")
            return r.get("title_eng") or r.get("title_rus") or r.get("id")
        return {"items": [{"id": r["id"], "title": title_of(r)} for r in rows if r.get("id")]}

    def rows_set_selected(self, row_id: str):
        self._selected_row_id = row_id or ""
        return {"ok": True}

    # ── каталоги/локации для UI
    def list_categories(self):
        try:
            lm = _safe_import(f"core.servers.{self.server}.locations_map")
            if lm and hasattr(lm, "get_categories"):
                return {"items": lm.get_categories(lang=self.language)}
        except Exception:
            pass
        r = _safe_import(f"core.servers.{self.server}.templates.resolver")
        if not r: return {"items": []}
        items = []
        for name in r.listdir(self.language, "dashboard", "teleport", "villages"):
            if not name.startswith("."):
                items.append({"id": name, "display_rus": name, "display_eng": name})
        return {"items": items}

    def list_locations(self, category_id: str):
        try:
            lm = _safe_import(f"core.servers.{self.server}.locations_map")
            if lm and hasattr(lm, "get_locations"):
                return {"items": lm.get_locations(category_id, lang=self.language)}
        except Exception:
            pass
        r = _safe_import(f"core.servers.{self.server}.templates.resolver")
        if not r: return {"items": []}
        out = []
        for f in (r.listdir(self.language, "dashboard", "teleport", "villages", category_id) or []):
            if f.lower().endswith(".png"):
                name = f.rsplit(".", 1)[0]
                out.append({"id": name, "display_rus": name, "display_eng": name, "filename": f})
        return {"items": out}


def launch_gui_html(local_version: str):
    base = os.path.join(os.path.dirname(__file__), "webui")
    html_path = os.path.join(base, "index.html")
    if not os.path.isfile(html_path):
        raise FileNotFoundError(f"UI not found: {html_path}")
    api = Bridge(local_version)
    webview.create_window(
        title=f"Revive · {local_version}",
        url=f"file://{html_path}",
        width=760, height=800, resizable=False,
        js_api=api,
    )
    webview.start(gui="edgechromium", debug=False)
