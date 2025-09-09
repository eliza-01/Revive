# app/launcher/sections/system.py
from __future__ import annotations
import threading
import json
from typing import Any, Dict
from ..base import BaseSection

from core.arduino.connection import ReviveController
from core.servers import get_server_profile, list_servers
from core.vision.capture.gdi import find_window, get_window_info
from core.arduino.connection_test import run_test_command
from core.updater import get_remote_version, is_newer_version

from core.state.pool import pool_merge

# отключили архивные зависимости
TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"

def _schedule(fn, ms: int):
    t = threading.Timer(max(0.0, ms) / 1000.0, fn)
    t.daemon = True
    t.start()

class SystemSection(BaseSection):
    """
    Инициализация контроллера и “бэк-сервисов”.
    Экспортирует:
      - get_init_state, set_language, set_server, find_window, test_connect
      - account_get/account_save
      - get_state_snapshot, get_status_snapshot
      - run_update_check
      - shutdown
    Остальные разделы (respawn/buffer/macros/tp/autofarm) — отдельные секции.
    """

    def __init__(self, window, local_version: str, controller: ReviveController,
                 ps_adapter,  # новый адаптер состояния игрока
                 sys_state: Dict[str, Any], schedule):
        super().__init__(window, sys_state)
        self.s.setdefault("version", local_version)
        self.s.setdefault("language", "rus")
        self.s.setdefault("server", (list_servers() or ["boh"])[0])
        self.s.setdefault("_last_status", {})

        # дефолты фич
        self.s.setdefault("respawn_enabled", True)
        self.s.setdefault("respawn_wait_enabled", False)
        self.s.setdefault("respawn_wait_seconds", 120)
        self.s.setdefault("buff_enabled", False)
        self.s.setdefault("buff_mode", "profile")
        self.s.setdefault("buff_method", "")
        self.s.setdefault("macros_enabled", False)
        self.s.setdefault("macros_run_always", False)
        self.s.setdefault("macros_delay_s", 1.0)
        self.s.setdefault("macros_duration_s", 2.0)
        self.s.setdefault("macros_sequence", ["1"])
        self.s.setdefault("tp_enabled", False)
        self.s.setdefault("tp_method", TP_METHOD_DASHBOARD)
        self.s.setdefault("tp_category", "")
        self.s.setdefault("tp_location", "")
        self.s.setdefault("tp_row_id", "")

        self.controller = controller
        self.ps = ps_adapter
        self.schedule = schedule

        # — server profile —
        self._apply_profile(self.s["server"])

        pool_merge(self.s, "features.buff", {"mode": self.s.get("buff_method", ""),
                                             "enabled": bool(self.s.get("buff_enabled", False))})
        # — Arduino ping status —
        try:
            self.controller.send("ping")
            ok = (self.controller.read() == "pong")
            self.emit("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
        except Exception as e:
            self.emit("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        # — автопоиск окна + периодическая проверка апдейта —
        _schedule(self._autofind_tick, 10)
        _schedule(self._periodic_update_check, 2_000)

        # — аккаунт (in-memory) —
        self.s.setdefault("account", {"login": "", "password": "", "pin": ""})

    # ---------- profile helpers ----------
    def _apply_profile(self, server: str):
        self.s["server"] = (server or "l2mad").lower()
        self.s["profile"] = get_server_profile(self.s["server"])
        # методы бафа (UI init)
        try:
            methods = list(getattr(self.s["profile"], "buff_supported_methods", lambda: [])())
            cur = getattr(self.s["profile"], "get_buff_mode", lambda: "")()
            if cur not in methods:
                cur = methods[0] if methods else ""
            self.s["buff_method"] = cur
            self.s["buff_methods"] = methods
        except Exception:
            self.s["buff_method"] = ""
            self.s["buff_methods"] = []

    # ---------- auto-find window ----------
    def _autofind_tick(self):
        if self.s.get("_autofind_stop") or self.s.get("window_found"):
            return
        self.find_window()
        if not self.s.get("window_found"):
            _schedule(self._autofind_tick, 3000)

    # ---------- update check ----------
    def _periodic_update_check(self):
        try:
            rv = get_remote_version()
            if is_newer_version(rv, self.s["version"]):
                self.emit("update", f"Доступно обновление: {rv}", None)
            else:
                self.emit("update", f"Установлена последняя версия: {self.s['version']}", True)
        except Exception:
            self.emit("update", "Сбой проверки актуальности версии", False)
        finally:
            _schedule(self._periodic_update_check, 600_000)

    # ---------- API: init / language / server ----------
    def get_init_state(self) -> Dict[str, Any]:
        servers = list_servers() or ["boh"]
        if self.s["server"] not in servers:
            self._apply_profile(servers[0])

        # повторный ping при первом заходе
        if "driver" not in self.s["_last_status"]:
            try:
                self.controller.send("ping")
                ok = (self.controller.read() == "pong")
                self.emit("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
            except Exception as e:
                self.emit("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        return {
            "version": self.s["version"],
            "language": self.s["language"],
            "server": self.s["server"],
            "servers": servers,
            "window_found": bool(self.s.get("window_found")),
            "monitoring": bool(self.ps.is_running() if hasattr(self.ps, "is_running") else self.s.get("_ps_running", False)),
            "buff_methods": self.s.get("buff_methods") or [],
            "buff_current": self.s.get("buff_method") or "",
            "tp_methods": [TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER],
            "driver_status": self.s["_last_status"].get("driver", {"text": "Состояние связи: неизвестно", "ok": None}),
            # ⬇️ конфиг респавна для UI
            "respawn": {
                "enabled": bool(self.s.get("respawn_enabled", False)),
                "wait_enabled": bool(self.s.get("respawn_wait_enabled", False)),
                "wait_seconds": int(self.s.get("respawn_wait_seconds", 120)),
            },
        }

    def set_language(self, lang: str):
        self.s["language"] = (lang or "rus").lower()
        try: self.ps.set_language(self.s["language"])
        except Exception: pass

    def set_server(self, server: str):
        self._apply_profile(server)
        try: self.ps.set_server(self.s["server"])
        except Exception: pass
        # обновить список методов бафа на UI
        methods = self.s.get("buff_methods") or []
        cur = self.s.get("buff_method") or ""
        try:
            self.window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onBuffMethods({json.dumps(methods)}, {json.dumps(cur)})")
        except Exception:
            pass

    # ---------- API: window / test ----------
    def find_window(self) -> Dict[str, Any]:
        titles = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
        for t in titles:
            hwnd = find_window(t)
            if hwnd:
                win_info = get_window_info(hwnd, client=True) or {}
                # гарантируем наличие hwnd — это критично для window_focus
                try:
                    win_info["hwnd"] = int(hwnd)
                except Exception:
                    pass
                if isinstance(win_info, dict) and all(k in win_info for k in ("x", "y", "width", "height")):
                    self.s["window"] = win_info
                    self.s["window_found"] = True
                    self.emit("window", "[✓] Окно найдено", True)
                    pool_merge(self.s, "window", {"info": win_info, "found": True})
                    return {"found": True, "title": t, "info": win_info}

        self.s["window"] = None
        self.s["window_found"] = False
        self.emit("window", "[×] Окно не найдено", False)
        print("[window dump] None")
        self.emit("window", "dump: None", None)
        pool_merge(self.s, "window", {"info": None, "found": False})
        return {"found": False}

    def test_connect(self) -> str:
        label_proxy = type("L", (), {"config": lambda *_a, **_k: None})
        run_test_command(self.controller, label_proxy)
        return "ok"

    # ---------- API: account ----------
    def account_get(self) -> Dict[str, str]:
        return dict(self.s.get("account") or {"login":"", "password":"", "pin":""})

    def account_save(self, data: Dict[str, str]):
        self.s["account"] = {
            "login": data.get("login",""),
            "password": data.get("password",""),
            "pin": data.get("pin",""),
        }

    # ---------- API: status / snapshot / update ----------
    def get_status_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.s.get("_last_status") or {})

    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        ВАЖНО: ps.last() возвращает dict, а не объект.
        Предыдущая версия читала через getattr(...) и из-за этого
        отдавала hp=0 → мигание в UI (перезапись корректного on_update).
        """
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

    # ---------- API: update ----------
    def run_update_check(self) -> Dict[str, Any]:
        try:
            rv = get_remote_version()
            newer = is_newer_version(rv, self.s["version"])
            return {"remote": rv, "local": self.s["version"], "update": bool(newer)}
        except Exception as e:
            return {"error": str(e)}

    # ---------- shutdown ----------
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

    # ---------- utils ----------
    def emit(self, scope: str, text: str, ok):
        payload = {"scope": scope, "text": text, "ok": (True if ok is True else False if ok is False else None)}
        self.s["_last_status"][scope] = payload
        js = f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})"
        try: self.window.evaluate_js(js)
        except Exception: pass

    def expose(self) -> dict:
        # методы, которые отдаём в webview
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
