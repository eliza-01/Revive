# app/launcher/sections/system.py
from __future__ import annotations
import json
import threading
from typing import Any, Dict, List
from pathlib import Path

from ..base import BaseSection

# core
from core.connection import ReviveController
from core.servers.registry import get_server_profile, list_servers
from core.vision.capture.gdi import find_window, get_window_info
from core.connection_test import run_test_command
from core.updater import get_remote_version, is_newer_version

from core.features.flow_orchestrator import FlowOrchestrator
from core.features.restart_manager import RestartManager
from core.features.post_tp_row import PostTPRowRunner, RowsController
from core.features.to_village import ToVillage
from core.runtime.state_watcher import StateWatcher
from core.checks.charged import ChargeChecker, BuffTemplateProbe
from core.features.autobuff_service import AutobuffService

from core.features.tp_after_respawn import (
    TP_METHOD_DASHBOARD,
    TP_METHOD_GATEKEEPER,
)

def _schedule(fn, ms: int):
    t = threading.Timer(max(0.0, ms) / 1000.0, fn)
    t.daemon = True
    t.start()

class SystemSection(BaseSection):
    """
    Инициализация контроллера, вотчера и общих сервисов.
    Экспортирует:
      - get_init_state, set_language, set_server, find_window, test_connect
      - account_get / account_save
      - watcher_is_running, get_state_snapshot, get_status_snapshot
      - run_update_check
      - shutdown, _py_exit

    Все прочие домены (respawn/buff/macros/tp/autofarm) — в отдельных секциях.
    """
    def __init__(self, window, local_version: str):
        super().__init__(window, sys_state={
            "version": local_version,
            "language": "rus",
            "server": (list_servers() or ["l2mad"])[0],
            "profile": None,

            # окно клиента
            "window": None,              # dict: {"x","y","width","height"}
            "window_found": False,
            "_autofind_stop": False,

            # учётные данные (in-memory)
            "account": {"login": "", "password": "", "pin": ""},

            # UI flags
            "respawn_enabled": True,
            "buff_enabled": False,
            "buff_mode": "profile",
            "buff_method": "",
            "buff_methods": [],
            "macros_enabled": False,
            "macros_run_always": False,
            "macros_delay_s": 1.0,
            "macros_duration_s": 2.0,
            "macros_sequence": ["1"],
            "tp_enabled": False,
            "tp_method": TP_METHOD_DASHBOARD,
            "tp_category": "",
            "tp_location": "",
            "tp_row_id": "",

            # кэш статусов для UI snapshot
            "_last_status": {},

            # хук для AutobuffService → реальный run_once определит buff-секция
            "_buff_run_once": None,
            "_charged_flag": None,
        })

        # --- controller ---
        self.s["controller"] = ReviveController()

        # --- server profile ---
        self._apply_profile(self.s["server"])

        # --- watcher ---
        self.s["watcher"] = StateWatcher(
            server=self.s["server"],
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s["language"],
            poll_interval=0.2,
            zero_hp_threshold=0.01,
            on_state=lambda st: None,
            on_dead=self._on_dead_proxy,
            on_alive=self._on_alive_proxy,
            debug=True,
        )

        # --- checker + buff probes (общие) ---
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

        # --- сервисы верхнего уровня (общие) ---
        self.s["to_village"] = ToVillage(
            controller=self.s["controller"],
            server=self.s["server"],
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s["language"],
            click_threshold=0.87,
            debug=True,
            is_alive=lambda: self.s["watcher"].is_alive(),
            confirm_timeout_s=3.0,
        )
        self.s["postrow"] = PostTPRowRunner(
            controller=self.s["controller"],
            server=self.s["server"],
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s["language"],
            on_status=lambda msg, ok=None: self.emit("postrow", msg, ok),
            on_finished=lambda: None,  # arm AF выполнит секция автофарма
        )
        self.s["restart"] = RestartManager(
            controller=self.s["controller"],
            get_server=lambda: self.s["server"],
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s["language"],
            watcher=self.s["watcher"],
            account_getter=lambda: self.s.get("account") or {"login": "", "password": "", "pin": ""},
            max_restart_attempts=3,
            retry_delay_s=1.0,
            logger=print,
        )
        self.s["orch"] = FlowOrchestrator(
            schedule=lambda fn, ms: _schedule(fn, ms),
            log=print,
            checker=self.s["checker"],
            watcher=self.s["watcher"],
            to_village=self.s["to_village"],
            postrow_runner=self.s["postrow"],
            restart_manager=self.s["restart"],
            get_server=lambda: self.s["server"],
            get_language=lambda: self.s["language"],
        )
        self.s["autobuff"] = AutobuffService(
            checker=self.s["checker"],
            is_alive=lambda: self.s["watcher"].is_alive(),
            buff_is_enabled=lambda: bool(self.s["buff_enabled"]),
            buff_run_once=lambda: self._buff_run_once_hook(),
            on_charged_update=lambda v: self.s.__setitem__("_charged_flag", v),
            tick_interval_s=1.0,
            log=print,
        )

        # rows controller (общая шина «маршрутов после ТП»)
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

        # --- Arduino ping status ---
        try:
            self.s["controller"].send("ping")
            ok = (self.s["controller"].read() == "pong")
            self.emit("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
        except Exception as e:
            self.emit("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        # --- авто-поиск окна и периодическая проверка обновлений ---
        _schedule(self._autofind_tick, 10)
        _schedule(self._periodic_update_check, 2_000)

    # ===== profile helpers =====
    def _apply_profile(self, server: str):
        self.s["server"] = (server or "l2mad").lower()
        self.s["profile"] = get_server_profile(self.s["server"])
        # методы бафа для UI
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

    # ===== rows → UI =====
    def _rows_set_values(self, rows: List[tuple[str, str]]):
        js = f"window.ReviveUI && window.ReviveUI.onRows({json.dumps(rows)})"
        try:
            self.window.evaluate_js(js)
        except Exception:
            pass

    def _set_tp_row_id(self, rid: str):
        self.s["tp_row_id"] = rid
        try:
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onRowSelected({json.dumps(rid)})"
            )
        except Exception:
            pass

    # ===== watcher hooks → orchestrator =====
    def _on_dead_proxy(self, st):
        # если хотите учитывать занятость — добавьте проверку; здесь делегируем сразу
        self.s["orch"].on_dead(st)

    def _on_alive_proxy(self, st):
        self.s["orch"].on_alive(st)
        # arm автофарм после ТП делает AF-секция через свой callback

    def set_buff_run_once_delegate(self, fn):
        """
        Регистрирует делегат 'баф один раз', который будет вызван AutobuffService.
        Ожидается сигнатура: () -> bool
        """
        if fn is not None and not callable(fn):
            raise TypeError("buff_run_once delegate must be callable or None")
        self.s["_buff_run_once"] = fn

    # ===== Autobuff hook (делегат в buff-секцию) =====
    def _buff_run_once_hook(self) -> bool:
        """
        Хук, который AutobuffService вызывает по расписанию/событию.
        Здесь мы безопасно дергаем зарегистрированный делегат из баф-секции.
        """
        try:
            fn = self.s.get("_buff_run_once")
            if callable(fn):
                return bool(fn())
        except Exception:
            pass
        return False

    # ===== auto-find window =====
    def _autofind_tick(self):
        if self.s.get("_autofind_stop") or self.s.get("window_found"):
            return
        self.find_window()
        if not self.s.get("window_found"):
            _schedule(self._autofind_tick, 3000)

    # ===== periodic update check =====
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

    # ===== Public API =====
    # --- init / language / server ---
    def get_init_state(self) -> Dict[str, Any]:
        servers = list_servers() or ["l2mad"]
        if self.s["server"] not in servers:
            self._apply_profile(servers[0])

        # если ещё не публиковали driver-статус — продублируем быстрый ping
        if "driver" not in (self.s["_last_status"] or {}):
            try:
                self.s["controller"].send("ping")
                ok = (self.s["controller"].read() == "pong")
                self.emit("driver", "[✓] Arduino ответила" if ok else "[×] Нет ответа", ok)
            except Exception as e:
                self.emit("driver", f"[×] Ошибка связи с Arduino: {e}", False)

        return {
            "version": self.s["version"],
            "language": self.s["language"],
            "server": self.s["server"],
            "servers": servers,
            "window_found": bool(self.s["window_found"]),
            "monitoring": bool(self.s["watcher"].is_running()),
            "buff_methods": self.s.get("buff_methods") or [],
            "buff_current": self.s.get("buff_method") or "",
            "tp_methods": [TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER],
            "driver_status": (self.s["_last_status"].get("driver")
                              or {"text": "Состояние связи: неизвестно", "ok": None}),
        }

    def set_language(self, lang: str):
        self.s["language"] = (lang or "rus").lower()
        try:
            self.s["watcher"].set_language(self.s["language"])
        except Exception:
            pass

    def set_server(self, server: str):
        self._apply_profile(server)
        try:
            self.s["watcher"].set_server(self.s["server"])
        except Exception:
            pass
        try:
            self.s["to_village"].set_server(self.s["server"])
        except Exception:
            pass
        # Пушим в UI новые методы бафа/текущий
        methods = self.s.get("buff_methods") or []
        cur = self.s.get("buff_method") or ""
        try:
            self.window.evaluate_js(
                f"window.ReviveUI && window.ReviveUI.onBuffMethods({json.dumps(methods)}, {json.dumps(cur)})"
            )
        except Exception:
            pass

    # --- window / test ---
    def find_window(self) -> Dict[str, Any]:
        titles = ["Lineage", "Lineage II", "L2MAD", "L2", "BOHPTS"]
        for t in titles:
            hwnd = find_window(t)
            if hwnd:
                info = get_window_info(hwnd, client=True)
                if all(k in info for k in ("x", "y", "width", "height")):
                    self.s["window"] = info
                    self.s["window_found"] = True
                    self.emit("window", f"[✓] Окно найдено: {t} ({info['width']}x{info['height']})", True)
                    return {"found": True, "title": t, "info": info}
        self.s["window"] = None
        self.s["window_found"] = False
        self.emit("window", "[×] Окно не найдено", False)
        return {"found": False}

    def test_connect(self) -> str:
        label_proxy = type("L", (), {"config": lambda *_a, **_k: None})
        run_test_command(self.s["controller"], label_proxy)  # побочные эффекты → статус драйвера
        return "ok"

    # --- account ---
    def account_get(self) -> Dict[str, str]:
        return dict(self.s.get("account") or {"login": "", "password": "", "pin": ""})

    def account_save(self, data: Dict[str, str]):
        self.s["account"] = {
            "login": data.get("login", ""),
            "password": data.get("password", ""),
            "pin": data.get("pin", ""),
        }

    # --- watcher / state / status ---
    def watcher_is_running(self) -> bool:
        try:
            return bool(self.s["watcher"].is_running())
        except Exception:
            return False

    def get_state_snapshot(self) -> Dict[str, Any]:
        try:
            st = self.s["watcher"].last()
            hp_ratio = float(getattr(st, "hp_ratio", 0.0) or 0.0)
            alive = bool(getattr(st, "alive", True))
            hp = max(0, min(100, int(round(hp_ratio * 100))))
            return {"hp": hp, "cp": 100, "alive": alive}
        except Exception:
            return {"hp": None, "cp": None, "alive": None}

    def get_status_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return dict(self.s.get("_last_status") or {})

    # --- update (одноразовая ручная проверка) ---
    def run_update_check(self) -> Dict[str, Any]:
        try:
            rv = get_remote_version()
            newer = is_newer_version(rv, self.s["version"])
            return {"remote": rv, "local": self.s["version"], "update": bool(newer)}
        except Exception as e:
            return {"error": str(e)}

    # --- lifecycle ---
    def shutdown(self):
        # остановить периодики
        self.s["_autofind_stop"] = True
        # обнулим делегат, чтобы не висел
        self.s["_buff_run_once"] = None
        # сервисы
        try:
            self.s["rows_ctrl"].stop()
        except Exception:
            pass
        try:
            self.s["autobuff"].stop()
        except Exception:
            pass
        try:
            self.s["watcher"].stop()
        except Exception:
            pass
        # порт
        try:
            self.s["controller"].close()
        except Exception:
            pass

    def _py_exit(self):
        self.shutdown()
        try:
            self.window.destroy()
        except Exception:
            pass

    # ===== интеграция с BaseSection.emit =====
    # BaseSection.emit(scope, text, ok) уже должен:
    #   - класть payload в self.s["_last_status"][scope]
    #   - пушить в UI: window.ReviveUI.onStatus({scope,text,ok})
    # Здесь переопределять не требуется.
