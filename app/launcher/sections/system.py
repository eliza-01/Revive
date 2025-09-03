# app/launcher/sections/system.py
from __future__ import annotations
import os, sys, json, threading
from typing import Any, Dict, List
from pathlib import Path
from ..base import BaseSection

from core.connection import ReviveController
from core.servers.registry import get_server_profile, list_servers
from core.vision.capture.gdi import find_window, get_window_info
from core.connection_test import run_test_command
from core.updater import get_remote_version, is_newer_version

from core.features.afterbuff_macros import AfterBuffMacroRunner
from core.features.flow_orchestrator import FlowOrchestrator
from core.features.restart_manager import RestartManager
from core.features.post_tp_row import PostTPRowRunner, RowsController
from core.features.to_village import ToVillage
from core.runtime.state_watcher import StateWatcher
from core.checks.charged import ChargeChecker, BuffTemplateProbe

from core.features.tp_after_respawn import TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER

def _schedule(fn, ms: int):
    t = threading.Timer(max(0.0, ms) / 1000.0, fn)
    t.daemon = True
    t.start()

class SystemSection(BaseSection):
    """
    Инициализация контроллера, вотчера и “бэк-сервисов”.
    Экспортирует:
      - get_init_state, set_language, set_server, find_window, test_connect
      - account_get/account_save
      - get_state_snapshot, get_status_snapshot
      - run_update_check
      - shutdown, _py_exit
    Остальные разделы (respawn/buff/macros/tp/autofarm) — отдельные секции.
    """
    def __init__(self, window, local_version: str, controller: ReviveController,
                 watcher: StateWatcher, orch: FlowOrchestrator,
                 sys_state: Dict[str, Any], schedule):
        super().__init__(window, sys_state)
        self.s.setdefault("version", local_version)
        self.s.setdefault("language", "rus")
        self.s.setdefault("server", (list_servers() or ["l2mad"])[0])
        self.s.setdefault("_last_status", {})
        self.s.setdefault("respawn_enabled", True)
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
        self.watcher = watcher
        self.orch = orch
        self.schedule = schedule

        # — server profile —
        self._apply_profile(self.s["server"])

        # — checker + buff probes —
        self.s["checker"] = ChargeChecker(interval_minutes=10, mode="ANY")
        self.s["checker"].register_probe(
            "autobuff_icons",
            BuffTemplateProbe(
                name="autobuff_icons",
                server_getter=lambda: self.s["server"],
                get_window=lambda: self.s.get("window"),
                get_language=lambda: self.s["language"],
                zone_key="buff_bar",
                tpl_keys=["buff_icon_shield", "buff_icon_blessedBody"],
                threshold=0.85,
                debug=True,
            ),
            enabled=True,
        )

        # — service: to_village, postrow, restart уже созданы снаружи; rows —
        self.s["rows_ctrl"] = RowsController(
            get_server=lambda: self.s["server"],
            get_language=lambda: self.s["language"],
            get_destination=lambda: (self.s["tp_category"], self.s["tp_location"]),
            schedule=lambda fn, ms: _schedule(fn, ms),
            on_values=self._rows_set_values,
            on_select_row_id=lambda rid: self._set_tp_row_id(rid or ""),
            log=print,
        )
        self.s["rows_ctrl"].start()

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

    # ---------- rows UI ----------
    def _rows_set_values(self, rows: List[tuple[str, str]]):
        js = f"window.ReviveUI && window.ReviveUI.onRows({json.dumps(rows)})"
        try: self.window.evaluate_js(js)
        except Exception: pass

    def _set_tp_row_id(self, rid: str):
        self.s["tp_row_id"] = rid
        try:
            self.window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onRowSelected({json.dumps(rid)})")
        except Exception:
            pass

    # ---------- watchers → orch ----------
    def _on_dead_proxy(self, st):
        self.orch.on_dead(st)

    def _on_alive_proxy(self, st):
        self.orch.on_alive(st)
        # arm автофарма после ТП делает секция автофарма

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
        servers = list_servers() or ["l2mad"]
        if self.s["server"] not in servers:
            self._apply_profile(servers[0])

        # если ещё не было driver-статуса — продублируем ping
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
            "monitoring": bool(self.watcher.is_running()),
            "buff_methods": self.s.get("buff_methods") or [],
            "buff_current": self.s.get("buff_method") or "",
            "tp_methods": [TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER],
            "driver_status": self.s["_last_status"].get("driver", {"text": "Состояние связи: неизвестно", "ok": None}),
        }

    def set_language(self, lang: str):
        self.s["language"] = (lang or "rus").lower()
        try: self.watcher.set_language(self.s["language"])
        except Exception: pass

    def set_server(self, server: str):
        self._apply_profile(server)
        try: self.watcher.set_server(self.s["server"])
        except Exception: pass
        try:
            # ToVillage зависит от сервера, если снаружи держится один экземпляр — уведомим его через профайл здесь не лезем
            pass
        except Exception:
            pass
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
                info = get_window_info(hwnd, client=True)
                if all(k in info for k in ("x","y","width","height")):
                    self.s["window"] = info
                    self.s["window_found"] = True
                    self.emit("window", "[✓] Окно найдено", True)
                    return {"found": True, "title": t, "info": info}
        self.s["window"] = None
        self.s["window_found"] = False
        self.emit("window", "[×] Окно не найдено", False)
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
        try:
            st = self.watcher.last()
            hp_ratio = float(getattr(st, "hp_ratio", 0.0) or 0.0)
            alive = bool(getattr(st, "alive", True))
            return {"hp": max(0, min(100, int(round(hp_ratio*100)))), "cp": 100, "alive": alive}
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
            self.watcher.stop()
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
