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
        self._window_info = None  # dict|None

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
        self._tp_enabled
