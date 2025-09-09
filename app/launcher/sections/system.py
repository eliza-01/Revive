# app/launcher/sections/system.py
from __future__ import annotations
import threading
import json
from typing import Any, Dict, Optional
from ..base import BaseSection

from core.arduino.connection import ReviveController
from core.servers import get_server_profile, list_servers
from core.vision.capture.gdi import find_window, get_window_info
from core.arduino.connection_test import run_test_command
from core.updater import get_remote_version, is_newer_version

from core.state.pool import pool_write, pool_get, ensure_pool

TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"

def _schedule(fn, ms: int):
    t = threading.Timer(max(0.0, ms) / 1000.0, fn)
    t.daemon = True
    t.start()

class SystemSection(BaseSection):
    """
    Инициализация контроллера и бэк-сервисов. Весь конфиг/состояние — в пуле.
    Экспорт: get_init_state, set_language, set_server, find_window, test_connect,
             account_get/account_save, get_state_snapshot, get_status_snapshot,
             run_update_check, shutdown
    """

    def __init__(self, window, local_version: str, controller: ReviveController,
                 ps_adapter, state: Dict[str, Any], schedule):
        super().__init__(window, state)
        ensure_pool(self.s)

        servers = list_servers() or ["boh"]
        server = pool_get(self.s, "config.server", servers[0])
        language = pool_get(self.s, "config.language", "rus")
        profile = get_server_profile(server)

        # app/config
        pool_write(self.s, "app", {"version": local_version})
        pool_write(self.s, "config", {"server": server, "language": language, "profile": profile, "profiles": servers})

        # respawn defaults (если кто-то не выставил раньше)
        pool_write(self.s, "features.respawn", {
            "enabled": bool(pool_get(self.s, "features.respawn.enabled", True)),
            "wait_enabled": bool(pool_get(self.s, "features.respawn.wait_enabled", False)),
            "wait_seconds": int(pool_get(self.s, "features.respawn.wait_seconds", 120)),
            "click_threshold": float(pool_get(self.s, "features.respawn.click_threshold", 0.70)),
            "confirm_timeout_s": float(pool_get(self.s, "features.respawn.confirm_timeout_s", 6.0)),
        })

        # buff methods from profile
        try:
            methods = list(getattr(profile, "buff_supported_methods", lambda: [])())
            cur = getattr(profile, "get_buff_mode", lambda: "")()
            if cur not in methods:
                cur = methods[0] if methods else ""
        except Exception:
            methods, cur = [], ""
        pool_write(self.s, "features.buff", {"methods": methods, "mode": cur})

        # pipeline defaults
        pool_write(self.s, "pipeline", {
            "allowed": list(pool_get(self.s, "pipeline.allowed", ["respawn","buff","macros","tp","autofarm"])),
            "order": list(pool_get(self.s, "pipeline.order", ["respawn","macros"])),
        })

        self.controller = controller
        self.ps = ps_adapter
        self.schedule = schedule

        # Arduino ping status
        try:
            self.controller.send("ping")
            ok = (self.controller.read() == "pong")
            self.emit("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
        except Exception as e:
            self.emit("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        # авто-поиск окна + периодическая проверка апдейта
        _schedule(self._autofind_tick, 10)
        _schedule(self._periodic_update_check, 2_000)

        # account init
        if not pool_get(self.s, "account.login", None):
            pool_write(self.s, "account", {"login": "", "password": "", "pin": ""})

    # ---------- helpers ----------
    def _apply_profile(self, server: str):
        server = (server or "boh").lower()
        profile = get_server_profile(server)
        pool_write(self.s, "config", {"server": server, "profile": profile})

        try:
            methods = list(getattr(profile, "buff_supported_methods", lambda: [])())
            cur = getattr(profile, "get_buff_mode", lambda: "")()
            if cur not in methods:
                cur = methods[0] if methods else ""
        except Exception:
            methods, cur = [], ""
        pool_write(self.s, "features.buff", {"methods": methods, "mode": cur})

    # ---------- auto-find window ----------
    def _autofind_tick(self):
        if self.s.get("_autofind_stop") or pool_get(self.s, "window.found", False):
            return
        self.find_window()
        if not pool_get(self.s, "window.found", False):
            _schedule(self._autofind_tick, 3000)

    # ---------- update check ----------
    def _periodic_update_check(self):
        try:
            local_v = pool_get(self.s, "app.version", "")
            rv = get_remote_version()
            newer = is_newer_version(rv, local_v)
            pool_write(self.s, "app.update", {"available": bool(newer), "remote": rv})
            self.emit("update",
                      f"Доступно обновление: {rv}" if newer else f"Установлена последняя версия: {local_v}",
                      None if newer else True)
        except Exception:
            self.emit("update", "Сбой проверки актуальности версии", False)
        finally:
            _schedule(self._periodic_update_check, 600_000)

    # ---------- API ----------
    def get_init_state(self) -> Dict[str, Any]:
        servers = list_servers() or ["boh"]
        cur_server = pool_get(self.s, "config.server", servers[0])

        # повторный ping при первом заходе
        last = pool_get(self.s, "ui_status", {})
        if not last or not (last.get("driver") and last["driver"].get("text")):
            try:
                self.controller.send("ping")
                ok = (self.controller.read() == "pong")
                self.emit("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
            except Exception as e:
                self.emit("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        return {
            "version": pool_get(self.s, "app.version", ""),
            "language": pool_get(self.s, "config.language", "rus"),
            "server": cur_server,
            "servers": servers,
            "window_found": bool(pool_get(self.s, "window.found", False)),
            "monitoring": bool(self.ps.is_running() if hasattr(self.ps, "is_running") else False),
            "buff_methods": pool_get(self.s, "features.buff.methods", []),
            "buff_current": pool_get(self.s, "features.buff.mode", ""),
            "tp_methods": [TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER],
            "driver_status": pool_get(self.s, "ui_status.driver", {"text": "Состояние связи: неизвестно", "ok": None}),
            "respawn": {
                "enabled": bool(pool_get(self.s, "features.respawn.enabled", False)),
                "wait_enabled": bool(pool_get(self.s, "features.respawn.wait_enabled", False)),
                "wait_seconds": int(pool_get(self.s, "features.respawn.wait_seconds", 120)),
            },
        }

    def set_language(self, lang: str):
        lang = (lang or "rus").lower()
        pool_write(self.s, "config", {"language": lang})
        try:
            self.ps.set_language(lang)
        except Exception:
            pass

    def set_server(self, server: str):
        self._apply_profile(server)
        try:
            self.ps.set_server(pool_get(self.s, "config.server", "boh"))
        except Exception:
            pass
        # ui: обновить методы бафа
        methods = pool_get(self.s, "features.buff.methods", [])
        cur = pool_get(self.s, "features.buff.mode", "")
        try:
            self.window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onBuffMethods({json.dumps(methods)}, {json.dumps(cur)})")
        except Exception:
            pass

    def find_window(self) -> Dict[str, Any]:
        titles = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
        for t in titles:
            hwnd = find_window(t)
            if hwnd:
                win_info = get_window_info(hwnd, client=True) or {}
                try:
                    win_info["hwnd"] = int(hwnd)
                except Exception:
                    pass
                if isinstance(win_info, dict) and all(k in win_info for k in ("x", "y", "width", "height")):
                    pool_write(self.s, "window", {"info": win_info, "found": True, "title": t})
                    self.emit("window", "[✓] Окно найдено", True)
                    return {"found": True, "title": t, "info": win_info}
        pool_write(self.s, "window", {"info": None, "found": False, "title": ""})
        self.emit("window", "[×] Окно не найдено", False)
        return {"found": False}

    def test_connect(self) -> str:
        label_proxy = type("L", (), {"config": lambda *_a, **_k: None})
        run_test_command(self.controller, label_proxy)
        return "ok"

    def account_get(self) -> Dict[str, str]:
        return dict(pool_get(self.s, "account", {"login": "", "password": "", "pin": ""}))

    def account_save(self, data: Dict[str, str]):
        pool_write(self.s, "account", {
            "login": data.get("login",""),
            "password": data.get("password",""),
            "pin": data.get("pin",""),
        })

    def get_status_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return dict(pool_get(self.s, "ui_status", {}) or {})

    def get_state_snapshot(self) -> Dict[str, Any]:
        try:
            st = self.ps.last() or {}
            hp_ratio = st.get("hp_ratio")
            if hp_ratio is None:
                return {"hp": None, "cp": None, "alive": None}
            hp = max(0, min(100, int(round(float(hp_ratio) * 100))))
            alive_val = st.get("alive")
            alive = bool(alive_val) if alive_val is not None else (hp > 0)
            return {"hp": hp, "cp": 100, "alive": alive}
        except Exception:
            return {"hp": None, "cp": None, "alive": None}

    def run_update_check(self) -> Dict[str, Any]:
        try:
            remote = get_remote_version()
            local = pool_get(self.s, "app.version", "")
            newer = is_newer_version(remote, local)
            pool_write(self.s, "app.update", {"available": bool(newer), "remote": remote})
            return {"remote": remote, "local": local, "update": bool(newer)}
        except Exception as e:
            return {"error": str(e)}

    def shutdown(self) -> None:
        try:
            self.s["_autofind_stop"] = True
            if hasattr(self.ps, "stop"):
                self.ps.stop()
        except Exception:
            pass
        try:
            self.controller.close()
        except Exception:
            pass

    # ---- utils ----
    def emit(self, scope: str, text: str, ok: Optional[bool]):
        payload = {"scope": scope, "text": text, "ok": (True if ok is True else False if ok is False else None)}
        try:
            self.window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})")
        except Exception:
            pass
        pool_write(self.s, f"ui_status.{scope}", {"text": text, "ok": payload["ok"]})

    def expose(self) -> dict:
        return {
            "get_init_state": self.get_init_state,
            "set_language": self.set_language,
            "set_server": self.set_server,
            "find_window": self.find_window,
            "test_connect": self.test_connect,
            "account_get": self.account_get,
            "account_save": self.account_save,
            "get_state_snapshot": self.get_state_snapshot,
            "get_status_snapshot": self.get_status_snapshot,
            "run_update_check": self.run_update_check,
            "shutdown": self.shutdown,
        }
