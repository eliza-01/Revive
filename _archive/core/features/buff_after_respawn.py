# _archive/core/features/buff_after_respawn.py
from __future__ import annotations
from typing import Callable, Optional, Dict
import importlib

from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow
from core.logging import console

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
        click_threshold: float = 0.87,
        debug: bool = False,
    ):
        self.controller = controller
        self.server = server
        self._get_window = get_window
        self._get_language = get_language
        self._click_thr = float(click_threshold)
        self._debug = bool(debug)

        self._mode = BUFF_MODE_PROFILE
        self._method = "dashboard"  # 'dashboard' | 'npc'

    def set_mode(self, mode: str):
        m = (mode or BUFF_MODE_PROFILE).lower()
        self._mode = m if m in (BUFF_MODE_PROFILE, BUFF_MODE_MAGE, BUFF_MODE_FIGHTER) else BUFF_MODE_PROFILE

    def set_method(self, method: str):
        m = (method or "dashboard").lower()
        self._method = m if m in ("dashboard", "npc") else "dashboard"

    def _mode_teleportl_key(self) -> str:
        return {
            BUFF_MODE_PROFILE: "buffer_mode_profile",
            BUFF_MODE_MAGE: "buffer_mode_mage",
            BUFF_MODE_FIGHTER: "buffer_mode_fighter",
        }[self._mode]

    def _load_flow(self):
        try:
            if self._method == "dashboard":
                try:
                    mod = importlib.import_module(f"core.servers.{self.server}.flows.buff_dashboard")
                except Exception:
                    mod = importlib.import_module(f"core.servers.{self.server}.flows.buffer")
            else:
                mod = importlib.import_module(f"core.servers.{self.server}.flows.buff_npc")
            return getattr(mod, "FLOW", [])
        except Exception as e:
            console.log(f"[buffer] load flow error: {e}")
            return []

    def _load_zones(self):
        try:
            zm = importlib.import_module(f"core.servers.{self.server}.zones.buffer")
            zones = getattr(zm, "ZONES", {})
            templates = getattr(zm, "TEMPLATES", {})
            return zones, templates
        except Exception as e:
            console.log(f"[buffer] zones load error: {e}")
            return {}, {}

    def run_once(self) -> bool:
        flow = self._load_flow()
        if not flow:
            console.log("[buffer] empty flow (nothing to do)")
            return False

        zones, templates = self._load_zones()
        if not zones or not templates:
            return False

        ctx = FlowCtx(
            server=self.server,
            controller=self.controller,
            get_window=self._get_window,
            get_language=self._get_language,
            zones=zones,
            templates=templates,
            extras={"mode_key_provider": lambda: self._mode_teleportl_key()},
        )
        execu = FlowOpExecutor(ctx)
        ok = run_flow(flow, execu)
        console.log("Баф выполнен" if ok else "Баф не выполнен")
        return ok
