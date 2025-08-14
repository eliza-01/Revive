# core/features/buff_after_respawn.py
from __future__ import annotations
import importlib
import time
from typing import Callable, Optional, Dict, Tuple

from core.runtime.dashboard_guard import DASHBOARD_GUARD
from core.vision.matching.template_matcher import match_in_zone

from core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow


BUFF_MODE_PROFILE = "profile"
BUFF_MODE_MAGE = "mage"
BUFF_MODE_FIGHTER = "fighter"

class BuffAfterRespawnWorker:
    def __init__(
            self,
            controller,
            server: str,
            get_window: Callable[[], Optional[Dict]],
            get_language: Callable[[], str],
            on_status: Callable[[str, Optional[bool]], None] = lambda *_: None,
            click_threshold: float = 0.87,
            debug: bool = False,
    ):
        self.controller = controller
        self.server = server
        self._get_window = get_window
        self._get_language = get_language
        self._on_status = on_status
        self.click_threshold = click_threshold or 0.82
        self.debug = debug

        self._zones = {}
        self._templates = {}
        self._flow = None
        self._mode = BUFF_MODE_PROFILE
        self.window: Optional[Dict] = None
        self._tag = "[buff]"
        self._load_cfg()

    def _log(self, msg: str) -> None:
        try:
            print(msg)
        except Exception:
            pass

    def _probe_left_click(self) -> None:
        try:
            self.controller.send("l")  # пробный левый клик
        except Exception:
            pass

    def set_mode(self, mode: str):
        m = (mode or BUFF_MODE_PROFILE).lower()
        self._mode = m if m in (BUFF_MODE_PROFILE, BUFF_MODE_MAGE, BUFF_MODE_FIGHTER) else BUFF_MODE_PROFILE

    def set_method(self, _method: str):
        pass  # только dashboard

    def run_once(self) -> bool:
        self.window = self._get_window() or {}
        if not self.window:
            self._on_status("[buff] window missing", False)
            return False

        if not self._flow:
            self._on_status("[buff] flow missing", False)
            return False

        with DASHBOARD_GUARD.session():
            return self._run_flow()

    # ---------- internals ----------
    def _load_cfg(self):
        try:
            mod = importlib.import_module(f"core.servers.{self.server}.zones.buff")
            self._zones = getattr(mod, "ZONES", {})
            self._templates = getattr(mod, "TEMPLATES", {})
        except Exception as e:
            print(f"[buff] zones/templates load error: {e}")
            self._zones, self._templates = {}, {}

        # flow опционален
        try:
            flow_mod = importlib.import_module(f"core.servers.{self.server}.flows.buff")
            self._flow = getattr(flow_mod, "FLOW", None)
        except Exception:
            self._flow = None

        if self.debug:
            print(f"[buff] cfg loaded for {self.server}. flow={'yes' if self._flow else 'no'}")

    def _lang(self) -> str:
        try:
            return (self._get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _mode_tpl_key(self) -> str:
        return {
            BUFF_MODE_PROFILE: "buffer_mode_profile",
            BUFF_MODE_MAGE: "buffer_mode_mage",
            BUFF_MODE_FIGHTER: "buffer_mode_fighter",
        }[self._mode]

    def _zone_ltrb(self, zone_decl):
        win = self.window or {}
        if isinstance(zone_decl, tuple) and len(zone_decl) == 4:
            return tuple(map(int, zone_decl))
        if isinstance(zone_decl, dict):
            ww, wh = int(win.get("width", 0)), int(win.get("height", 0))
            if zone_decl.get("fullscreen"):
                return (0, 0, ww, wh)
            if zone_decl.get("centered"):
                w, h = int(zone_decl["width"]), int(zone_decl["height"])
                l = ww // 2 - w // 2
                t = wh // 2 - h // 2
                return (l, t, l + w, t + h)
            l = int(zone_decl.get("left", 0))
            t = int(zone_decl.get("top", 0))
            w = int(zone_decl.get("width", 0))
            h = int(zone_decl.get("height", 0))
            return (l, t, l + w, t + h)
        return (0, 0, int(win.get("width", 0)), int(win.get("height", 0)))

    def _is_visible(self, zone_key: str, tpl_key_or_parts, thr: float) -> bool:
        zone = self._zones.get(zone_key)
        if not zone:
            return False
        ltrb = self._zone_ltrb(zone)
        parts = tpl_key_or_parts
        if isinstance(parts, str):
            parts = self._templates.get(parts, [])
        if not parts:
            return False
        return match_in_zone(self.window, ltrb, self.server, self._lang(), parts, thr) is not None

    def _wait_in(self, zone_key: str, tpl_key: str, timeout_ms: int, thr: float) -> bool:
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if self._is_visible(zone_key, tpl_key, thr):
                return True
            time.sleep(0.05)
        return False

    def _wait_while_visible(self, zone_key: str, tpl_key: str, timeout_ms: int, thr: float) -> bool:
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if not self._is_visible(zone_key, tpl_key, thr):
                return True
            time.sleep(0.1)
        return False

    def _wait_template(self, zone_key: str, tpl_key: str, timeout_ms: int, thr: float = None) -> bool:
        zone = self._zones.get(zone_key); tpl = self._templates.get(tpl_key)
        if not zone or not tpl:
            return False
        ltrb = self._zone_ltrb(zone)
        thr = self.click_threshold if thr is None else float(thr)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if match_in_zone(self.window, ltrb, self.server, self._lang(), tpl, thr):
                return True
            time.sleep(0.05)
        return False

    def _click_in(self, zone_key: str, tpl_key: str, timeout_ms: int, thr: float = None) -> bool:
        zone = self._zones.get(zone_key); tpl = self._templates.get(tpl_key)
        if not zone or not tpl:
            return False
        ltrb = self._zone_ltrb(zone)
        thr = self.click_threshold if thr is None else float(thr)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            pt = match_in_zone(self.window, ltrb, self.server, self._lang(), tpl, thr)
            if pt:
                self.controller.send(f"click:{pt[0]},{pt[1]}")
                return True
            time.sleep(0.05)
        return False

    def _click_any(self, zone_keys, tpl_key: str, timeout_ms: int, thr: float = None) -> bool:
        thr = self.click_threshold if thr is None else float(thr)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            for zk in zone_keys:
                if self._click_in(zk, tpl_key, 1, thr):
                    return True
            time.sleep(0.05)
        return False

    def _dashboard_reset(self):
        self._log("[buff] dashboard reset")
        thr = self.click_threshold
        while True:
            self.controller.send("b")  # dashboard_close
            time.sleep(0.5)
            self.controller.send("b")  # dashboard_init
            time.sleep(0.5)
            if not self._is_visible("dashboard_body", "dashboard_init", thr):
                continue
            self.controller.send("b")  # close again
            time.sleep(0.5)
            if not self._is_visible("dashboard_body", "dashboard_init", thr):
                break
        self._log("[buff] dashboard reset done")
    # ---------- flow engine ----------
    def _run_flow(self) -> bool:
        while True:
            ctx = FlowCtx(
                server=self.server,
                controller=self.controller,
                get_window=self._get_window,
                get_language=self._get_language,
                zones=self._zones,
                templates=self._templates,
                extras={"mode_key_provider": self._mode_tpl_key},
            )
            execu = FlowOpExecutor(ctx, on_status=self._on_status, logger=self._log)
            ok = run_flow(self._flow, execu)
            if ok:
                self._log("[buff] flow DONE")
                self._on_status("[buff] done", True)
                return True
            self._log("[buff] flow failed → dashboard reset")
            self._dashboard_reset()
