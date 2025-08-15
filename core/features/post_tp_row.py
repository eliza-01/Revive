# core/features/post_tp_row.py
from __future__ import annotations
import importlib, time
from typing import Callable, Optional, Dict, List, Any
from core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

class PostTPRowRunner:
    def __init__(self, controller, server: str, get_window, get_language, on_status=lambda *_: None):
        self.controller = controller
        self.server = server
        self.get_window = get_window
        self.get_language = get_language
        self._on_status = on_status

    def set_server(self, server: str): self.server = server

    def run_row(self, village_id: str, location_id: str, row_id: str) -> bool:
        try:
            zones_mod = importlib.import_module(f"core.servers.{self.server}.zones.tp")
            zones = getattr(zones_mod, "ZONES", {})
            templates = getattr(zones_mod, "TEMPLATES", {})
        except Exception:
            zones, templates = {}, {}

        # flow лежит: core/servers/<server>/flows/rows/<village>/<location>/<row_id>.py
        mod_path = f"core.servers.{self.server}.flows.rows.{village_id}.{location_id}.{row_id}"
        try:
            flow_mod = importlib.import_module(mod_path)
            flow = getattr(flow_mod, "FLOW", None)
        except Exception as e:
            self._on_status(f"[rows] flow load error: {e}", False)
            return False
        if not flow:
            self._on_status("[rows] flow missing", False)
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
