# app/launcher_html.py
# === FILE: app/launcher_html.py
from __future__ import annotations
import os
import sys
import json
import time
import threading
import logging
from typing import Optional, Tuple, Dict, List, Any, Callable
from pathlib import Path
import webview  # pywebview / WebView2
import subprocess, tempfile, ctypes
import ctypes, subprocess, tempfile, os
from pathlib import Path

# --- core runtime ---
from core.connection import ReviveController
from core.connection_test import run_test_command
from core.servers.registry import get_server_profile, list_servers
from core.runtime.state_watcher import StateWatcher
from core.checks.charged import ChargeChecker, BuffTemplateProbe
from core.features.afterbuff_macros import AfterBuffMacroRunner
from core.features.post_tp_row import PostTPRowRunner, RowsController
from core.features.to_village import ToVillage
from core.features.flow_orchestrator import FlowOrchestrator
from core.features.restart_manager import RestartManager
from core.features.autobuff_service import AutobuffService

# --- TP lists (как в Tk-версии) ---
from core.features.tp_after_respawn import TPAfterDeathWorker, TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER
from core.servers.l2mad.locations_map import get_categories as tp_get_categories, get_locations as tp_get_locations

# --- capture / window ---
from core.vision.capture.gdi import find_window, get_window_info

# --- updater (используется только для проверки наличия апдейта) ---
from core.updater import get_remote_version, is_newer_version

from core.engines.autofarm.zone_repo import get_zone_info as af_get_zone_info
from core.engines.autofarm.zone_repo import list_zones_declared
from core.engines.autofarm.skill_repo import list_skills as af_list_skills
from core.engines.autofarm.skill_repo import list_professions as af_list_profs
from core.engines.autofarm.skill_repo import debug_professions as af_debug_profs
from core.engines.autofarm.service import AutoFarmService
from core.engines.autofarm.runner import run_af_click_button as af_run_click

LOG_PATH = "revive.log"
logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s")

def _res_path(*parts: str) -> str:
    # путь к ресурсам как в PyInstaller (onefile) так и в dev
    base = os.path.join(getattr(sys, "_MEIPASS", ""), "app") if hasattr(sys, "_MEIPASS") else os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, *parts)

def _schedule(fn: Callable[[], None], ms: int) -> None:
    t = threading.Timer(max(0.0, ms) / 1000.0, fn)
    t.daemon = True
    t.start()


class Bridge:
    """
    JS ↔ Python мост для HTML UI.
    Совпадает по возможностям с Tk-версией: мониторинг, баф, макросы, ТП, post-ТП маршрут, апдейтер, аккаунт.
    """
    def __init__(self, window: webview.Window, local_version: str):
        self.window = window
        self.local_version = local_version

        # --- app state ---
        servers = list_servers() or ["l2mad"]
        self.server: str = servers[0]
        self.language: str = "rus"
        self._charged_flag: Optional[bool] = None
        self.account: Dict[str, str] = {"login": "", "password": "", "pin": ""}

        # --- controller ---
        self.controller = ReviveController()

        # --- server profile ---
        self.profile = get_server_profile(self.server)

        # --- window info / probe ---
        self._window_info: Optional[Dict[str, Any]] = None
        self._window_found: bool = False
        self._autofind_stop = False

        # --- watcher ---
        self.watcher = StateWatcher(
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            poll_interval=0.2,
            zero_hp_threshold=0.01,
            on_state=lambda st: None,
            on_dead=self._on_dead_proxy,
            on_alive=self._on_alive_proxy,
            debug=True,
        )

        # --- checker + probes ---
        self.checker = ChargeChecker(interval_minutes=10, mode="ANY")
        self.checker.register_probe(
            "autobuff_icons",
            BuffTemplateProbe(
                name="autobuff_icons",
                server_getter=lambda: self.server,
                get_window=lambda: self._safe_window(),
                get_language=lambda: self.language,
                zone_key="buff_bar",
                tpl_keys=["buff_icon_shield", "buff_icon_blessedBody"],
                threshold=0.85,
                debug=True,
            ),
            enabled=True,
        )

        # --- services/workers ---
        self.postrow = PostTPRowRunner(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            on_status=lambda msg, ok: self._emit_status("postrow", msg, ok),
            on_finished=lambda: self._af_after_tp()   # ← НОВОЕ
        )
        self.to_village = ToVillage(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            click_threshold=0.87,
            debug=True,
            is_alive=lambda: self.watcher.is_alive(),
            confirm_timeout_s=3.0,
        )

        self.restart = RestartManager(
            controller=self.controller,
            get_server=lambda: self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            watcher=self.watcher,
            account_getter=lambda: self.account,
            max_restart_attempts=3,
            retry_delay_s=1.0,
            logger=self._log,
        )

        self.orch = FlowOrchestrator(
            schedule=lambda fn, ms: _schedule(fn, ms),
            log=self._log,
            checker=self.checker,
            watcher=self.watcher,
            to_village=self.to_village,
            postrow_runner=self.postrow,
            restart_manager=self.restart,
            get_server=lambda: self.server,
            get_language=lambda: self.language,
        )
        self._last_status: Dict[str, Dict[str, Any]] = {}
        self.orch.set_autofarm_start(lambda: self.af_start())

        # --- AutoFarm сервис (гейт перед стартом) ---
        self.autofarm = AutoFarmService(
            controller=self.controller,
            get_server=lambda: self.server,
            get_language=lambda: self.language,
            get_window=lambda: self._safe_window(),
            is_alive=lambda: self.watcher.is_alive(),
            schedule=_schedule,
            on_status=lambda text, ok=None: self._emit_status("af", text, ok),
            log=self._log,
        )
        # приоритеты: true -> шаг завершён
        # если у объекта нет is_running/is_busy — считаем, что готов.
        self.autofarm.register_pre_step("restart", lambda: not getattr(self.restart, "is_running", lambda: False)())
        self.autofarm.register_pre_step("to_village", lambda: not getattr(self.to_village, "is_running", lambda: False)())
        self.autofarm.register_pre_step("postrow", lambda: not getattr(self.postrow, "is_running", lambda: False)())
        self.autofarm.register_pre_step("autobuff", lambda: not getattr(self.autobuff, "is_busy", lambda: False)())

        # --- UI model ---
        self.ui: Dict[str, Any] = {
            # respawn
            "monitoring": False,
            "respawn_enabled": True,
            # buff
            "buff_enabled": False,
            "buff_mode": "profile",     # 'profile' | 'mage' | 'fighter'
            "buff_method": "",          # заполняется из профиля, если поддерживается
            # afterbuff macros
            "macros_enabled": False,
            "macros_run_always": False,
            "macros_delay_s": 1.0,
            "macros_duration_s": 2.0,
            "macros_sequence": ["1"],
            # tp
            "tp_enabled": False,
            "tp_method": TP_METHOD_DASHBOARD,  # dashboard|gatekeeper
            "tp_category": "",
            "tp_location": "",
            "tp_row_id": "",
        }

        self.afterbuff_runner = AfterBuffMacroRunner(
            controller=self.controller,
            get_sequence=lambda: list(self.ui["macros_sequence"]),
            get_delay_s=lambda: float(self.ui["macros_delay_s"]),
        )

        self.autobuff = AutobuffService(
            checker=self.checker,
            is_alive=lambda: self.watcher.is_alive(),
            buff_is_enabled=lambda: bool(self.ui["buff_enabled"]),
            buff_run_once=lambda: self.buff_run_once(),
            on_charged_update=lambda v: setattr(self, "_charged_flag", v),
            tick_interval_s=1.0,
            log=self._log,
        )

        # rows controller
        self.rows_ctrl: RowsController | None = RowsController(
            get_server=lambda: self.server,
            get_language=lambda: self.language,
            get_destination=lambda: self._tp_get_destination(),
            schedule=lambda fn, ms: _schedule(fn, ms),
            on_values=self._rows_set_values,
            on_select_row_id=lambda rid: self._set_tp_row_id(rid or ""),
            log=self._log,
        )
        self.rows_ctrl.start()

        # orchestrator UI hooks
        self.orch.set_ui(
            buff_is_enabled=lambda: bool(self.ui["buff_enabled"]),
            buff_run_once=self.buff_run_once,
            macros_ui_is_enabled=lambda: bool(self.ui["macros_enabled"]),
            macros_ui_run_always=lambda: bool(self.ui["macros_run_always"]),
            macros_ui_get_duration_s=lambda: float(self.ui["macros_duration_s"]),
            macros_run_once=self.macros_run_once,
            tp_is_enabled=lambda: bool(self.ui["tp_enabled"]),
            tp_teleport_now_selected=self.tp_teleport_now,
            tp_get_selected_destination=lambda: self._tp_get_destination(),
            tp_get_selected_row_id=lambda: str(self.ui["tp_row_id"] or ""),
            respawn_ui_is_enabled=lambda: bool(self.ui["respawn_enabled"]),
        )

        # попытка ping Arduino
        try:
            self.controller.send("ping")
            if self.controller.read() == "pong":
                self._emit_status("driver", "[✓] Arduino ответила", True)
            else:
                self._emit_status("driver", "[×] Нет ответа", False)
        except Exception as e:
            self._emit_status("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        # авто-поиск окна
        _schedule(self._autofind_tick, 10)

        # периодическая проверка обновлений
        _schedule(self._periodic_update_check, 2_000)

    # ---------- helpers ----------
    # ---------- не дает запускать что-либо пока цикл запущен
    def _is_cycle_busy(self) -> bool:
        """Любой из основных шагов в работе → занято."""
        try:
            if getattr(self.restart,  "is_running", lambda: False)(): return True
            if getattr(self.to_village,"is_running", lambda: False)(): return True
            if getattr(self.postrow,  "is_running", lambda: False)(): return True
            if getattr(self.autobuff, "is_busy",   lambda: False)(): return True
        except Exception:
            pass
        return False

    def _on_dead_proxy(self, st):
        if self._is_cycle_busy():
            self._emit_status("watcher", "[flow] busy → skip on_dead", None)
            return
        self.orch.on_dead(st)

    def _on_alive_proxy(self, st):
        if self._is_cycle_busy():
            self._emit_status("watcher", "[flow] busy → skip on_alive", None)
            try: self.autofarm.notify_after_tp()
            except Exception: pass
            return
        self.orch.on_alive(st)
        try:
            self.autofarm.notify_after_tp()
        except Exception:
            pass

    def buff_run_once(self) -> bool:
        if self._is_cycle_busy():
            self._emit_status("buff", "Занято основным циклом", False)
            return False
        if not self._window_found:
            self._emit_status("buff", "Окно не найдено", False)
            return False
        w = self._ensure_buff_worker()
        ok = w.run_once()
        self._emit_status("buff", "Баф выполнен" if ok else "Баф не выполнен", ok)
        return bool(ok)

    def macros_run_once(self) -> bool:
        if self._is_cycle_busy():
            self._emit_status("macros", "Занято основным циклом", False)
            return False
        ok = self.afterbuff_runner.run_once()
        self._emit_status("macros", "Макросы выполнены" if ok else "Макросы не выполнены", ok)
        return bool(ok)

    def tp_teleport_now(self) -> bool:
        if self._is_cycle_busy():
            self._emit_status("tp", "Занято основным циклом", False)
            return False
    ############################

    def _log(self, *a):
        try:
            print(*a)
        except Exception:
            pass

    def _safe_window(self) -> Optional[Dict]:
        try:
            return self._window_info
        except Exception:
            return None

    def _emit_status(self, scope: str, text: str, ok: Optional[bool]) -> None:
        payload = {"scope": scope, "text": text, "ok": (True if ok is True else False if ok is False else None)}
        self._last_status[scope] = payload  # кэшируем, чтобы UI мог забрать после инициализации
        js = f"window.ReviveUI && window.ReviveUI.onStatus({json.dumps(payload)})"
        try:
            self.window.evaluate_js(js)
        except Exception:
            pass

    def get_status_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Вернуть последние статусы по scope."""
        return dict(self._last_status)

    def watcher_is_running(self) -> bool:
        try:
            return bool(self.watcher.is_running())
        except Exception:
            return False

    def _emit_rows(self, rows: List[Tuple[str, str]]) -> None:
        # rows: [(row_id, title)]
        js = f"window.ReviveUI && window.ReviveUI.onRows({json.dumps(rows)})"
        try:
            self.window.evaluate_js(js)
        except Exception:
            pass

    def _tp_get_destination(self) -> Tuple[str, str]:
        return (self.ui["tp_category"] or "", self.ui["tp_location"] or "")

    def _set_tp_row_id(self, rid: str):
        self.ui["tp_row_id"] = rid
        try:
            self.window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onRowSelected({json.dumps(rid)})")
        except Exception:
            pass

    def _rows_set_values(self, rows: List[Tuple[str, str]]):
        self._emit_rows(rows)

    def _autofind_tick(self):
        if self._autofind_stop or self._window_found:
            return
        self.find_window()
        if not self._window_found:
            _schedule(self._autofind_tick, 3000)

    def _af_after_tp(self):
        try:
            # запускать только если AF включён и режим "После ТП"
            if getattr(self, "autofarm", None) and self.autofarm.enabled and self.autofarm.mode == "after_tp":
                self.autofarm.arm()  # ← мягкий «вооружить»; реальный старт сделает сервис
        except Exception as e:
            self._emit_status("af", f"[AF] arm after TP failed: {e}", False)

    def _periodic_update_check(self):
        try:
            rv = get_remote_version()
            if is_newer_version(rv, self.local_version):
                msg = f"Доступно обновление: {rv}"
                self._emit_status("update", msg, None)
            else:
                self._emit_status("update", f"Установлена последняя версия: {self.local_version}", True)
        except Exception:
            self._emit_status("update", "Сбой проверки актуальности версии", False)
        finally:
            _schedule(self._periodic_update_check, 600_000)

    # ---------- watcher → orchestrator ----------
    def _on_dead_proxy(self, st):
        self.orch.on_dead(st)

    def _on_alive_proxy(self, st):
        self.orch.on_alive(st)
        try:
            self.autofarm.notify_after_tp()
        except Exception:
            pass

    # ---------- JS API ----------
    def get_init_state(self) -> Dict[str, Any]:
        servers = list_servers() or ["l2mad"]
        if self.server not in servers:
            self.server = servers[0]
        # профиль и методы бафа
        self.profile = get_server_profile(self.server)
        methods, current = [], ""
        try:
            methods = list(getattr(self.profile, "buff_supported_methods", lambda: [])())
            cur = getattr(self.profile, "get_buff_mode", lambda: "")()
            current = cur if cur in methods else (methods[0] if methods else "")
            self.ui["buff_method"] = current
        except Exception:
            methods, current = [], ""

        # если статуса драйвера ещё нет — выполним быстрый ping здесь
        if "driver" not in self._last_status:
            try:
                self.controller.send("ping")
                ok = (self.controller.read() == "pong")
                self._emit_status("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
            except Exception as e:
                self._emit_status("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        return {
            "version": self.local_version,
            "language": self.language,
            "server": self.server,
            "servers": servers,
            "window_found": bool(self._window_found),
            "monitoring": bool(self.watcher.is_running()),
            "buff_methods": methods,
            "buff_current": current,
            "tp_methods": [TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER],
            "driver_status": self._last_status.get("driver", {"text": "Состояние связи: неизвестно", "ok": None}),
        }

    def set_language(self, lang: str) -> None:
        self.language = (lang or "rus").lower()
        try:
            self.watcher.set_language(self.language)
        except Exception:
            pass

    def set_server(self, server: str) -> None:
        self.server = (server or "l2mad").lower()
        self.profile = get_server_profile(self.server)
        try:
            self.watcher.set_server(self.server)
        except Exception:
            pass
        try:
            self.to_village.set_server(self.server)
        except Exception:
            pass
        # обновить список методов бафа и текущий
        methods = []
        cur = ""
        try:
            methods = list(getattr(self.profile, "buff_supported_methods", lambda: [])())
            cur = getattr(self.profile, "get_buff_mode", lambda: "")()
            if not cur or cur not in methods:
                cur = methods[0] if methods else ""
            self.ui["buff_method"] = cur
        except Exception:
            pass
        # push на UI
        self.window.evaluate_js(f"window.ReviveUI && window.ReviveUI.onBuffMethods({json.dumps(methods)}, {json.dumps(cur)})")

    def find_window(self) -> Dict[str, Any]:
        titles = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
        for t in titles:
            hwnd = find_window(t)
            if hwnd:
                info = get_window_info(hwnd, client=True)
                if all(k in info for k in ("x", "y", "width", "height")):
                    self._window_info = info
                    self._window_found = True
                    self._emit_status("window", "[✓] Окно найдено", True)
                    return {"found": True, "title": t, "info": info}
        self._window_info = None
        self._window_found = False
        self._emit_status("window", "[×] Окно не найдено", False)
        return {"found": False}

    def test_connect(self) -> str:
        # обновит статус внутри run_test_command
        label_proxy = type("L", (), {"config": lambda *_a, **_k: None})
        run_test_command(self.controller, label_proxy)  # side effects в порт
        return "ok"

    # --- account ---
    def account_get(self) -> Dict[str, str]:
        return dict(self.account)

    def account_save(self, data: Dict[str, str]) -> None:
        self.account.update({
            "login": data.get("login", ""),
            "password": data.get("password", ""),
            "pin": data.get("pin", ""),
        })

    # --- watcher controls ---
    def respawn_set_monitoring(self, enabled: bool) -> None:
        self.ui["monitoring"] = bool(enabled)
        if enabled and not self.watcher.is_running():
            self.watcher.start()
            self._emit_status("watcher", "[state] watcher ON", True)
        elif not enabled and self.watcher.is_running():
            self.watcher.stop()
            self._emit_status("watcher", "[state] watcher OFF", None)

    def respawn_set_enabled(self, enabled: bool) -> None:
        self.ui["respawn_enabled"] = bool(enabled)

    def get_state_snapshot(self) -> Dict[str, Any]:
        try:
            st = self.watcher.last()
            hp_ratio = float(getattr(st, "hp_ratio", 0.0) or 0.0)
            alive = bool(getattr(st, "alive", True))
            return {"hp": max(0, min(100, int(round(hp_ratio * 100)))) , "cp": 100, "alive": alive}
        except Exception:
            return {"hp": None, "cp": None, "alive": None}

    # --- buff ---
    def buff_set_enabled(self, enabled: bool) -> None:
        self.ui["buff_enabled"] = bool(enabled)

    def buff_set_mode(self, mode: str) -> None:
        self.ui["buff_mode"] = (mode or "profile").lower()

    def buff_set_method(self, method: str) -> None:
        self.ui["buff_method"] = method or ""
        try:
            if hasattr(self.profile, "set_buff_mode"):
                self.profile.set_buff_mode(self.ui["buff_method"])
        except Exception:
            pass

    def _ensure_buff_worker(self) -> "BuffAfterRespawnWorker":
        from core.features.buff_after_respawn import BuffAfterRespawnWorker, BUFF_MODE_PROFILE
        # создаём/обновляем каждый вызов
        if not hasattr(self, "_buff_worker") or self._buff_worker is None:
            def _status(text, ok=None):
                self._emit_status("buff", text, ok)
            self._buff_worker = BuffAfterRespawnWorker(
                controller=self.controller,
                server=self.server,
                get_window=lambda: self._safe_window(),
                get_language=lambda: self.language,
                on_status=_status,
                click_threshold=0.87,
                debug=True,
            )
        # sync динамику
        self._buff_worker.server = self.server
        self._buff_worker.set_mode(self.ui["buff_mode"])
        try:
            if self.ui.get("buff_method"):
                self._buff_worker.set_method(self.ui["buff_method"])
        except Exception:
            pass
        return self._buff_worker

    def buff_run_once(self) -> bool:
        if not self._window_found:
            self._emit_status("buff", "Окно не найдено", False)
            return False
        w = self._ensure_buff_worker()
        ok = w.run_once()
        self._emit_status("buff", "Баф выполнен" if ok else "Баф не выполнен", ok)
        return bool(ok)

    # --- afterbuff macros ---
    def macros_set_enabled(self, enabled: bool) -> None:
        self.ui["macros_enabled"] = bool(enabled)

    def macros_set_run_always(self, enabled: bool) -> None:
        self.ui["macros_run_always"] = bool(enabled)

    def macros_set_delay(self, seconds: float) -> None:
        try:
            self.ui["macros_delay_s"] = max(0.0, float(seconds))
        except Exception:
            pass

    def macros_set_duration(self, seconds: float) -> None:
        try:
            self.ui["macros_duration_s"] = max(0.0, float(seconds))
        except Exception:
            pass

    def macros_set_sequence(self, seq: List[str]) -> None:
        # фильтр по допустимым клавишам 0-9
        allowed = set("0123456789")
        cleaned = [c for c in (seq or []) if c and c[0] in allowed]
        self.ui["macros_sequence"] = cleaned or ["1"]

    def macros_run_once(self) -> bool:
        ok = self.afterbuff_runner.run_once()
        self._emit_status("macros", "Макросы выполнены" if ok else "Макросы не выполнены", ok)
        return bool(ok)

    # --- TP ---
    def tp_set_enabled(self, enabled: bool) -> None:
        self.ui["tp_enabled"] = bool(enabled)

    def tp_set_method(self, method: str) -> None:
        self.ui["tp_method"] = (method or TP_METHOD_DASHBOARD)

    def tp_set_category(self, cid: str) -> None:
        self.ui["tp_category"] = cid or ""
        # сбросить выбранную локацию
        self.ui["tp_location"] = ""

    def tp_set_location(self, lid: str) -> None:
        self.ui["tp_location"] = lid or ""

    def tp_get_categories(self) -> List[Dict[str, str]]:
        # завязка на l2mad карту, как и в Tk
        cats = tp_get_categories(lang=self.language)
        return [{"id": c["id"], "title": c["display_rus"] if self.language == "rus" else c["display_eng"]} for c in cats]

    def tp_get_locations(self, category_id: str) -> List[Dict[str, str]]:
        locs = tp_get_locations(category_id, lang=self.language) if category_id else []
        return [{"id": l["id"], "title": l["display_rus"] if self.language == "rus" else l["display_eng"]} for l in locs]

    def tp_get_selected_row_id(self) -> str:
        return str(self.ui["tp_row_id"] or "")

    def tp_set_selected_row_id(self, rid: str) -> None:
        self._set_tp_row_id(rid or "")

    def tp_teleport_now(self) -> bool:
        # локальный worker
        status_lock = threading.Lock()
        msg_holder = {"text": "", "ok": None}

        def _status(text, ok=None):
            with status_lock:
                msg_holder["text"] = text
                msg_holder["ok"] = ok
            self._emit_status("tp", text, ok)

        w = TPAfterDeathWorker(
            controller=self.controller,
            window_info=self._safe_window(),
            get_language=lambda: self.language,
            on_status=_status,
            check_is_dead=lambda: (not self.watcher.is_alive()),
        )
        w.set_method(self.ui["tp_method"])
        cat, loc = self._tp_get_destination()
        ok = w.teleport_now(cat, loc, self.ui["tp_method"])
        # статус уже отправлен через _status
        return bool(ok)

    # --- update ---
    def run_update_check(self) -> Dict[str, Any]:
        try:
            rv = get_remote_version()
            newer = is_newer_version(rv, self.local_version)
            return {"remote": rv, "local": self.local_version, "update": bool(newer)}
        except Exception as e:
            return {"error": str(e)}

    # --- shutdown ---
    def shutdown(self) -> None:
        try:
            self._autofind_stop = True
            self.watcher.stop()
        except Exception:
            pass
        try:
            self.autobuff.stop()
        except Exception:
            pass
        try:
            self.controller.close()
        except Exception:
            pass

    # -- попап инфо зоны автофарма
    def af_zone_info(self, zone_id: str, lang: str):
        server = getattr(self, "server", "") or getattr(self, "_server", "") or "common"
        return af_get_zone_info(server, zone_id, lang or "eng")

    # вернуть только объявленные в server/zones.json
    def af_list_zones_declared_only(self, lang: str):
        server = getattr(self, "server", "") or getattr(self, "_server", "") or ""
        return list_zones_declared(server, lang or "eng")

    def af_get_professions(self, lang: str = ""):
        try:
            lang = (lang or self.language or "eng")
            return af_list_profs(lang)
        except Exception as e:
            print(f"[autofarm] af_get_professions error: {e}")
            return []

    def af_professions_debug(self):
        return af_debug_profs()

    def af_get_attack_skills(self, profession: str, lang: str):
        server = getattr(self, "server", "") or getattr(self, "_server", "") or "common"
        return af_list_skills(profession, ["attack"], lang or "eng", server)

    #Автофарм
    def _autofarm_start_stub(self):
        # сюда подключится реальный движок: core/engines/autofarm/<server>/engine.py
        self._emit_status("af", "Старт автофарма (заглушка)", True)
        # пример: вызвать серверный сценарий
        # try:
        #     from core.engines.autofarm.<server>.engine import start as af_start
        #     af_start(self.controller, self._safe_window(), self.language, self.ui, self.account)
        # except Exception as e:
        #     self._emit_status("af", f"Не удалось запустить: {e}", False)
    def autofarm_set_mode(self, mode: str):
        self.autofarm.set_mode((mode or "after_tp").lower())

    def autofarm_set_enabled(self, enabled: bool):
        self.autofarm.set_enabled(bool(enabled))
        self._emit_status("af", "Включено" if enabled else "Выключено", True if enabled else None)

    def autofarm_validate(self, ui_state: Dict[str, Any]):
        # ui_state: {profession, skills:[{slug,...}], zone, ...}
        ok = True; reason = None
        if not ui_state.get("profession"):
            ok, reason = False, "Выберите профессию"
        elif not any((s.get("slug") for s in (ui_state.get("skills") or []))):
            ok, reason = False, "Добавьте атакующий скилл"
        elif not ui_state.get("zone"):
            ok, reason = False, "Выберите зону"
        return {"ok": ok, "reason": reason}

    def autofarm_save(self, ui_state: Dict[str, Any]):
        # сохраняем конфиг в сервисе, не включая/выключая
        self.autofarm.set_enabled(self.autofarm.enabled, ui_state or {})
        return {"ok": True}

    def af_start(self, mode: str = "after_tp") -> bool:
        """
        Заглушка: жмём кнопку автофарма через шаблон из движка.
        Позже сюда можно вставить ожидание окончания приоритетных флоу.
        """
        def _st(msg, ok=None): self._emit_status("postrow", f"[AF] {msg}", ok)
        return af_run_click(
            server=self.server,
            controller=self.controller,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            on_status=_st
        )

    # --- window close hook (called from JS) ---
    def _py_exit(self) -> None:
        self.shutdown()
        try:
            self.window.destroy()
        except Exception:
            pass
        sys.exit(0)

def _work_area_center(w: int, h: int) -> tuple[int, int]:
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    rect = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    x = rect.left + max(0, (rect.right - rect.left - w) // 2)
    y = rect.top  + max(0, (rect.bottom - rect.top - h) // 2)
    return int(x), int(y)

_SPLASH_PS = r"""param($gif)
Add-Type -Name U32 -Namespace Win -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[Win.U32]::SetProcessDPIAware() | Out-Null
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$u = (New-Object System.Uri($gif)).AbsoluteUri

# HTML фиксированной вёрстки 360x170, центрирование как в форме
$html = @"
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
html,body{margin:0;height:100%;background:#111;color:#fff}
.container{position:relative;width:360px;height:170px}
img{position:absolute;left:144px;top:28px;width:72px;height:72px}
p{position:absolute;top:110px;width:100%;text-align:center;font:900 13px 'Segoe UI', Tahoma, Verdana, system-ui}
</style></head>
<body>
<div class="container">
  <img src="$u" alt="">
  <p>Загрузка Revive…</p>
</div>
</body></html>
"@

# Окно
$w=360;$h=170
$wa=[System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$left=[int]($wa.Left + ($wa.Width - $w)/2)
$top =[int]($wa.Top  + ($wa.Height - $h)/2)

$form=New-Object System.Windows.Forms.Form
$form.FormBorderStyle=[System.Windows.Forms.FormBorderStyle]::None
$form.StartPosition=[System.Windows.Forms.FormStartPosition]::Manual
$form.BackColor=[System.Drawing.Color]::FromArgb(17,17,17)
$form.TopMost=$true
$form.Location=New-Object System.Drawing.Point($left,$top)
$form.Size=New-Object System.Drawing.Size($w,$h)
$form.ShowInTaskbar=$true

$wb = New-Object System.Windows.Forms.WebBrowser
$wb.ScrollBarsEnabled = $false
$wb.Dock = 'Fill'
$wb.ScriptErrorsSuppressed = $true
$form.Controls.Add($wb)
$wb.DocumentText = $html

[System.Windows.Forms.Application]::Run($form)
"""

def _spawn_splash(gif_path: str):
    import tempfile, os, subprocess
    from pathlib import Path
    try:
        fd, ps1 = tempfile.mkstemp(suffix=".ps1"); os.close(fd)
        with open(ps1, "w", encoding="utf-8") as f:
            f.write(_SPLASH_PS)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
             "-File", ps1, str(Path(gif_path))],
            creationflags=flags
        )
        return p, ps1
    except Exception:
        return None, None

def _kill_splash(p, hta_path: str|None):
    if p:
        try: p.terminate()
        except Exception: pass
        try: p.wait(timeout=1)
        except Exception: pass
    if hta_path and os.path.isfile(hta_path):
        try: os.remove(hta_path)
        except Exception: pass

def launch_gui(local_version: str):
    index_path = _res_path("webui", "index.html")
    if not os.path.exists(index_path):
        raise RuntimeError(f"Не найден UI: {index_path}")

    # 1) сплэш
    gif_path = _res_path("webui", "assets", "preloader1.gif")
    splash_proc, splash_tag = _spawn_splash(gif_path)

    def _close_splash(*_):
        _kill_splash(splash_proc, splash_tag)

    # 2) основное окно
    window = webview.create_window(
        title="Revive Launcher",
        url=index_path,
        width=820,
        height=900,
        resizable=False,
    )

    # 3) мост и API
    api = Bridge(window, local_version)
    window.expose(
        api.get_init_state, api.set_language, api.set_server, api.find_window, api.test_connect,
        api.account_get, api.account_save, api.respawn_set_monitoring, api.respawn_set_enabled,
        api.get_state_snapshot, api.get_status_snapshot, api.watcher_is_running,
        api.buff_set_enabled, api.buff_set_mode, api.buff_set_method, api.buff_run_once,
        api.macros_set_enabled, api.macros_set_run_always, api.macros_set_delay,
        api.macros_set_duration, api.macros_set_sequence, api.macros_run_once,
        api.tp_set_enabled, api.tp_set_method, api.tp_set_category, api.tp_set_location,
        api.tp_get_categories, api.tp_get_locations, api.tp_get_selected_row_id,
        api.tp_set_selected_row_id, api.tp_teleport_now, api.run_update_check,
        api.shutdown, api._py_exit,
        api.af_get_professions,
        api.af_get_attack_skills,
        api.af_list_zones_declared_only,
        api.af_zone_info,
        api.af_professions_debug,
        api.autofarm_set_mode, api.autofarm_set_enabled, api.autofarm_validate, api.autofarm_save,
        api.af_start,
    )

    # 4) события
    window.events.loaded  += _close_splash
    window.events.shown   += _close_splash

    def _on_closing():
        try:
            api.shutdown()
        finally:
            _close_splash()
            os._exit(0)

    window.events.closing += _on_closing

    # 5) запуск
    webview.start(debug=False, gui="edgechromium", http_server=True)




# точка входа при запуске как скрипт
if __name__ == "__main__":
    webview.start(debug=False, gui="edgechromium", http_server=True)
