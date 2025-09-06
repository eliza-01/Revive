# core/features/dashboard_reset.py
from __future__ import annotations
import importlib
from typing import Callable, Optional, Dict, List, Any
from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

class DashboardResetRunner:
    """
    Запускает flow core/servers/<server>/flows/dashboard_reset.py
    Использует зоны/шаблоны из zones.tp
    """
    def __init__(self, controller, server: str, get_window: Callable[[], Optional[Dict]],
                 get_language: Callable[[], str], on_status: Callable[[str, Optional[bool]], None] = lambda *_: None):
        self.controller = controller
        self.server = server
        self.get_window = get_window
        self.get_language = get_language
        self._on_status = on_status

    def set_server(self, server: str):
        self.server = server

    def run(self) -> bool:
        # зоны/шаблоны для дашборда
        try:
            zones_mod = importlib.import_module(f"core.servers.{self.server}.zones.tp")
            zones = getattr(zones_mod, "ZONES", {})
            templates = getattr(zones_mod, "TEMPLATES", {})
        except Exception:
            zones, templates = {}, {}

        # сам flow
        try:
            flow_mod = importlib.import_module(f"core.servers.{self.server}.flows.dashboard_reset")
            flow = getattr(flow_mod, "FLOW", None)
        except Exception as e:
            self._on_status(f"[reset] flow load error: {e}", False)
            return False
        if not flow:
            self._on_status("[reset] flow missing", False)
            return False

        ctx = FlowCtx(
            server=self.server,
            controller=self.controller,
            get_window=self.get_window,
            get_language=self.get_language,
            zones=zones,
            templates=templates,
            extras={},
        )
        execu = FlowOpExecutor(ctx, on_status=self._on_status, logger=lambda m: print(m))
        return run_flow(flow, execu)
