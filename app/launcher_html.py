# app/launcher_html.py
from __future__ import annotations
import os, importlib, threading, time, json
import webview

from core.connection import ReviveController
from core.connection_test import run_test_command
from core.servers.registry import list_servers, get_server_profile

# — бэкендные блоки (некоторые могут отсутствовать в твоей поставке)
try:
    from core.runtime.state_watcher import StateWatcher
except Exception:
    StateWatcher = None  # type: ignore
try:
    from core.checks.charged import ChargeChecker, BuffTemplateProbe
except Exception:
    ChargeChecker = BuffTemplateProbe = None  # type: ignore

try:
    from core.features.afterbuff_macros import AfterBuffMacroRunner
except Exception:
    AfterBuffMacroRunner = None  # type: ignore

try:
    from core.features.buff_after_respawn import BuffAfterRespawnWorker, BUFF_MODE_PROFILE, BUFF_MODE_MAGE, BUFF_MODE_FIGHTER
except Exception:
    BuffAfterRespawnWorker = None  # type: ignore
    BUFF_MODE_PROFILE = "profile"; BUFF_MODE_MAGE = "mage"; BUFF_MODE_FIGHTER = "fighter"

try:
    from core.features.tp_after_respawn import TPAfterDeathWorker, TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER
except Exception:
    TPAfterDeathWorker = None  # type: ignore
    TP_METHOD_DASHBOARD = "dashboard"; TP_METHOD_GATEKEEPER = "gatekeeper"

try:
    from core.features.post_tp_row import PostTPRowRunner
except Exception:
    PostTPRowRunner = None  # type: ignore

try:
    from core.features.to_village import ToVillage
except Exception:
    ToVillage = None  # type: ignore

# gdi helpers (поиск окна/инфа)
try:
    from core.vision.capture.gdi import find_window, get_window_info
except Exception:
    find_window = get_window_info = None  # type: ignore


# ────────────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНОЕ
# ────────────────────────────────────────────────────────────────────────────

class Repeater:
    """Простой планировщик без Tk: переодический вызов fn() в отдельном потоке."""
    def __init__(self, fn, interval_s: float):
        self.fn = fn; self.interval = max(0.05, float(interval_s))
        self._stop = threading.Event(); self._thr: threading.Thread|None = None
    def start(self):
        if self._thr and self._thr.is_alive(): return
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, daemon=True); self._thr.start()
    def stop(self):
        self._stop.set()
    def _loop(self):
        while not self._stop.is_set():
            try: self.fn()
            except Exception as e: print("[Repeater]", e)
            self._stop.wait(self.interval)


def _safe_import(modpath: str):
    try:
        return importlib.import_module(modpath)
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────────────
# BRIDGE
# ────────────────────────────────────────────────────────────────────────────

class Bridge:
    def __init__(self, version: str):
        self.version = version

        # состояние
        self.server_list = list_servers() or ["l2mad"]
        self.server = self.server_list[0]
        self.profile = get_server_profile(self.server)
        self.language = "rus"

        # железо/окно
        self.controller = ReviveController()
        self._window_info = None
        self._watcher = None
        self._last_state = None

        # watcher
        self._watcher = None
        if StateWatcher:
            self._watcher = StateWatcher(
                server=self.server,
                get_window=lambda: self._window_info,
                get_language=lambda: self.language,
                poll_interval=0.2,
                zero_hp_threshold=0.01,
                on_state=lambda st: None,
                on_dead=lambda st: print("[watcher] DEAD"),
                on_alive=lambda st: print("[watcher] ALIVE"),
                debug=False,
            )

        # checker + probe (для «заряжен/не заряжен»)
        self._checker = None
        if ChargeChecker and BuffTemplateProbe:
            self._checker = ChargeChecker(interval_minutes=10, mode="ANY")
            try:
                self._checker.register_probe(
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
            except Exception as e:
                print("[checker] probe init:", e)

        # баф
        self._buff_mode = BUFF_MODE_PROFILE
        self._buff_method = getattr(self.profile, "get_buff_mode", lambda: "dashboard")()
        self._buff_enabled = False

        # макросы после бафа
        self._macros_enabled = False
        self._macros_run_always = False
        self._macros_seq = ["1"]
        self._macros_delay_s = 1.0
        self._macros_duration_s = 2.0
        self._macros_runner = AfterBuffMacroRunner(self.controller, lambda: self._macros_seq, lambda: self._macros_delay_s) if AfterBuffMacroRunner else None

        # ТП
        self._tp_cfg = {"cat":"", "loc":"", "method":TP_METHOD_DASHBOARD}
        self._tp_enabled = False
        self._tp_worker = (TPAfterDeathWorker and TPAfterDeathWorker(
            controller=self.controller,
            window_info=self._window_info,
            get_language=lambda: self.language,
            on_status=lambda msg, ok=None: print(msg),
            check_is_dead=lambda: not self.is_alive().get("alive", True),
            wait_alive_timeout_s=0.5,
            server=self.server,
        )) or None

        # post-row runner (ручной запуск с UI)
        self._rows_runner = (PostTPRowRunner and PostTPRowRunner(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._window_info,
            get_language=lambda: self.language,
            on_status=lambda msg, ok=None: print(msg),
        )) or None

        # to_village (ручной подъём)
        self._to_village = (ToVillage and ToVillage(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._window_info,
            get_language=lambda: self.language,
            click_threshold=0.87,
            debug=False,
            is_alive=lambda: self.is_alive().get("alive", True),
            confirm_timeout_s=3.0,
        )) or None

        # автоповтор чекера
        self._checker_tick = Repeater(lambda: self._checker and self._checker.tick(), 1.0)


    # --- внутреннее ---
    def _ensure_watcher(self):
        if self._watcher is None:
            from core.runtime.state_watcher import StateWatcher
            # watcher будет обновлять self._last_state в фоне
            self._watcher = StateWatcher(
                server=self.server,
                get_window=lambda: self._window_info,
                get_language=lambda: self.language,
                poll_interval=0.25,
                on_state=lambda st: setattr(self, "_last_state", st),
            )
            self._watcher.start()
        return self._watcher
    # ─── системное ───
    def app_version(self):
        return {"version": self.version}

    def quit(self):
        try:
            self._checker_tick.stop()
        except Exception:
            pass
        try:
            self._watcher and self._watcher.stop()
        except Exception:
            pass
        try:
            self.controller.close()
        except Exception:
            pass
        os._exit(0)

    # ─── сервер / язык ───
    def list_servers(self):
        return {"items": self.server_list}

    def set_server(self, server: str):
        srv = (server or "l2mad").lower()
        if srv == self.server:
            return {"ok": True, "server": self.server}

        self.server = srv

        # профиль и дефолтный метод бафа
        try:
            self.profile = get_server_profile(self.server)
            cur = getattr(self.profile, "get_buff_mode", lambda: "")()
            if cur:
                self._buff_method = cur
        except Exception:
            pass

        # watcher
        try:
            if self._watcher:
                self._watcher.set_server(self.server)
        except Exception:
            pass

        # TP worker
        try:
            if self._tp_worker:
                if hasattr(self._tp_worker, "set_server"):
                    self._tp_worker.set_server(self.server)
                else:
                    setattr(self._tp_worker, "server", self.server)
                # актуализируем ссылку на окно
                if hasattr(self._tp_worker, "window"):
                    self._tp_worker.window = self._window_info
        except Exception:
            pass

        # Rows runner
        try:
            if self._rows_runner:
                self._rows_runner.set_server(self.server)
        except Exception:
            pass

        # ToVillage
        try:
            if self._to_village:
                self._to_village.set_server(self.server)
        except Exception:
            pass

        return {"ok": True, "server": self.server}

    def get_server(self):
        return {"server": self.server}

    def set_language(self, lang: str):
        self.language = (lang or "rus").lower()
        return {"ok": True, "language": self.language}

    # ─── окно клиента ───
    def find_window_now(self, titles: list[str] | None = None):
        titles = titles or ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
        found = False
        if not (find_window and get_window_info):
            return {"found": False, "error": "gdi unavailable"}
        for t in titles:
            try:
                hwnd = find_window(t)
                if hwnd:
                    info = get_window_info(hwnd, client=True)
                    if all(k in info for k in ("x","y","width","height")):
                        self._window_info = info
                        try:
                            if self._tp_worker and hasattr(self._tp_worker, "window"):
                                self._tp_worker.window = self._window_info
                        except Exception:
                            pass
                        found = True
                        break
            except Exception:
                pass
        return {"found": found, "window": (self._window_info or None)}

    def get_window(self):
        """Найти окно клиента и вернуть info. Вызывается из web-UI."""
        try:
            from core.vision.capture.gdi import find_window, get_window_info
            titles = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
            for t in titles:
                hwnd = find_window(t)
                if hwnd:
                    info = get_window_info(hwnd, client=True)
                    if all(k in info for k in ("x", "y", "width", "height")):
                        self._window_info = info
                        try:
                            if self._tp_worker and hasattr(self._tp_worker, "window"):
                                self._tp_worker.window = self._window_info
                        except Exception:
                            pass
                        try:
                            self._ensure_watcher()
                        except Exception:
                            pass
                        return {"found": True, "title": t, "info": info}
            return {"found": False}
        except Exception as e:
            return {"found": False, "error": str(e)}

    # ─── пинг ардуино / тест ───
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

    # ─── watcher / состояние ───
    def watcher_start(self):
        if self._watcher:
            self._watcher.start()
            return {"ok": True}
        return {"ok": False, "error": "watcher unavailable"}

    def watcher_stop(self):
        if self._watcher:
            self._watcher.stop()
            return {"ok": True}
        return {"ok": False, "error": "watcher unavailable"}

    def watcher_status(self):
        if not self._watcher:
            return {"running": False}
        try:
            return {"running": bool(self._watcher.is_running())}
        except Exception:
            return {"running": False}

    def state_last(self):
        """Вернуть последнее состояние от watcher (hp_ratio, is_alive)."""
        try:
            if self._watcher is None:
                # Попробуем автонайти окно и стартануть watcher
                self.get_window()
            st = self._last_state
            if not st:
                return {"hp_ratio": None, "is_alive": None}
            hp = float(getattr(st, "hp_ratio", 0.0) or 0.0)
            return {"hp_ratio": hp, "is_alive": bool(hp > 0.01)}
        except Exception as e:
            return {"hp_ratio": None, "is_alive": None, "error": str(e)}

    def is_alive(self):
        if not self._watcher:
            return {"alive": True}
        try:
            return {"alive": bool(self._watcher.is_alive())}
        except Exception:
            return {"alive": True}

    # ─── charged checker ───
    def checker_enable(self, enable: bool):
        if not self._checker:
            return {"ok": False}
        try:
            self._checker.set_enabled(bool(enable))
            if enable: self._checker_tick.start()
            else: self._checker_tick.stop()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def charged_now(self):
        if not self._checker:
            return {"charged": None}
        return {"charged": self._checker.force_check()}

    # ─── аккаунт ───
    def account_get(self):
        return {"account": getattr(self, "account", {"login":"", "password":"", "pin":""})}

    def account_set(self, login: str, password: str, pin: str):
        self.account = {"login": login or "", "password": password or "", "pin": pin or ""}
        return {"ok": True}

    # ─── баф ───
    def buff_supported_methods(self):
        try:
            methods = list(getattr(self.profile, "buff_supported_methods", lambda: [])())
            cur = getattr(self.profile, "get_buff_mode", lambda: "")()
            return {"methods": methods, "current": (cur or (methods[0] if methods else ""))}
        except Exception:
            return {"methods": ["dashboard"], "current": "dashboard"}

    def buff_set_mode(self, mode: str):
        mode = (mode or BUFF_MODE_PROFILE).lower()
        self._buff_mode = mode
        return {"ok": True}

    def buff_set_method(self, method: str):
        method = (method or "dashboard").lower()
        self._buff_method = method
        try:
            if hasattr(self.profile, "set_buff_mode"):
                self.profile.set_buff_mode(method)
        except Exception:
            pass
        return {"ok": True}

    def buff_enable(self, enable: bool):
        self._buff_enabled = bool(enable)
        return {"ok": True, "enabled": self._buff_enabled}

    def buff_run_once(self):
        if not BuffAfterRespawnWorker:
            return {"ok": False, "error": "buff worker unavailable"}
        worker = BuffAfterRespawnWorker(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._window_info,
            get_language=lambda: self.language,
            on_status=lambda msg, ok=None: print(msg),
            click_threshold=0.87,
            debug=False,
        )
        worker.set_mode(self._buff_mode)
        try:
            worker.set_method(self._buff_method)
        except Exception:
            pass
        ok = worker.run_once()
        return {"ok": bool(ok)}

    # ─── макросы после бафа ───
    def macros_config(self, enabled: bool, seq: list[str], delay_s: float, duration_s: float, run_always: bool):
        self._macros_enabled = bool(enabled)
        self._macros_seq = list(seq or ["1"])
        self._macros_delay_s = max(0.0, float(delay_s or 0.0))
        self._macros_duration_s = max(0.0, float(duration_s or 0.0))
        self._macros_run_always = bool(run_always)
        return {"ok": True}

    def macros_run_once(self):
        if not self._macros_runner:
            return {"ok": False, "error": "macros runner unavailable"}
        ok = self._macros_runner.run_once()
        return {"ok": bool(ok)}

    # ─── ТП ───
    def list_categories(self):
        try:
            lm = _safe_import(f"core.servers.{self.server}.locations_map")
            if lm and hasattr(lm, "get_categories"):
                return {"items": lm.get_categories(lang=self.language)}
        except Exception:
            pass
        # fallback через resolver
        r = _safe_import(f"core.servers.{self.server}.templates.resolver")
        if not r:
            return {"items": []}
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
        if not r:
            return {"items": []}
        out = []
        for f in (r.listdir(self.language, "dashboard", "teleport", "villages", category_id) or []):
            if f.lower().endswith(".png"):
                name = f.rsplit(".", 1)[0]
                out.append({"id": name, "display_rus": name, "display_eng": name, "filename": f})
        return {"items": out}

    def rows_list(self, village_id: str, location_id: str):
        mod = _safe_import(f"core.servers.{self.server}.flows.rows.registry")
        if not mod or not hasattr(mod, "list_rows"):
            return {"items": []}
        rows = mod.list_rows(village_id, location_id) or []
        lang = self.language
        def title_of(r):
            if lang == "rus":
                return r.get("title_rus") or r.get("id")
            return r.get("title_eng") or r.get("title_rus") or r.get("id")
        return {"items": [{"id": r["id"], "title": title_of(r)} for r in rows if r.get("id")]}

    def tp_configure(self, category_id: str, location_id: str, method: str):
        self._tp_cfg = {"cat": category_id or "", "loc": location_id or "", "method": (method or TP_METHOD_DASHBOARD)}
        if self._tp_worker:
            try: self._tp_worker.set_method(self._tp_cfg["method"])
            except Exception: pass
            try: self._tp_worker.configure(self._tp_cfg["cat"], self._tp_cfg["loc"], self._tp_cfg["method"])
            except Exception: pass
        return {"ok": True, **self._tp_cfg}

    def tp_now(self):
        if not self._tp_worker:
            return {"ok": False, "error": "tp worker unavailable"}
        ok = self._tp_worker.teleport_now(self._tp_cfg["cat"], self._tp_cfg["loc"], self._tp_cfg["method"])
        return {"ok": bool(ok)}

    # ─── ручной «встать в деревню» ───
    def to_village_now(self, timeout_ms: int = 14000):
        if not self._to_village:
            return {"ok": False, "error": "to_village unavailable"}
        ok = self._to_village.run_once(timeout_ms=timeout_ms)
        return {"ok": bool(ok)}


def launch_gui_html(local_version: str):
    base = os.path.join(os.path.dirname(__file__), "webui")
    html_path = os.path.join(base, "index.html")
    if not os.path.isfile(html_path):
        raise FileNotFoundError(f"UI not found: {html_path}")

    api = Bridge(local_version)
    window = webview.create_window(
        title=f"Revive · {local_version}",
        url=f"file://{html_path}",
        width=760, height=800, resizable=False,
        js_api=api,               # ← ВАЖНО: js_api здесь
    )
    webview.start(gui="edgechromium", debug=False)  # ← без js_api
