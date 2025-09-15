# _archive/core/features/flow_actions.py
from __future__ import annotations
import importlib
from typing import Callable, Optional, Dict, Any

from _archive.core.runtime.dashboard_guard import DASHBOARD_GUARD
from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow
from _archive.servers.l2mad.templates import resolver as l2mad_resolver
from core.logging import console


class FlowActions:
    def __init__(
        self,
        controller,
        server: str,
        get_window: Callable[[], Optional[Dict]],
        get_language: Callable[[], str],
    ):
        self.controller = controller
        self.server = server
        self.get_window = get_window
        self.get_language = get_language

    def _load(self, feature: str):
        zones = templates = flow = None
        try:
            zmod = importlib.import_module(f"core.servers.{self.server}.zones.{feature}")
            zones = getattr(zmod, "ZONES", {})
            templates = getattr(zmod, "TEMPLATES", {})
        except Exception as e:
            console.log(f"[flow] zones/templates load error: {e}")
            zones, templates = {}, {}
        try:
            fmod = importlib.import_module(f"core.servers.{self.server}.flows.{feature}")
            flow = getattr(fmod, "FLOW", None)
        except Exception as e:
            console.log(f"[flow] flow load error: {e}")
            flow = None
        return zones, templates, flow

    def _run(self, feature: str, extras: Dict[str, Any] = None, guard: bool = False) -> bool:
        zones, templates, flow = self._load(feature)
        if not flow:
            console.log(f"[{feature}] flow missing")
            return False
        ctx = FlowCtx(
            server=self.server,
            controller=self.controller,
            get_window=self.get_window,
            get_language=self.get_language,
            zones=zones,
            templates=templates,
            extras=extras or {},
        )
        execu = FlowOpExecutor(ctx)  # логирует в console.log
        if guard:
            DASHBOARD_GUARD.wait_free(timeout=10.0)
            with DASHBOARD_GUARD.session():
                return run_flow(flow, execu)
        return run_flow(flow, execu)

    # public APIs
    def buff(self, mode_key_provider) -> bool:
        return self._run("buffer", extras={"mode_key_provider": mode_key_provider}, guard=True)

    def teleport_dashboard(self, category_id: str, location_id: str) -> bool:
        return self._run(
            "teleport",
            extras={"resolver": l2mad_resolver.resolve, "category_id": category_id, "location_id": location_id},
            guard=True,
        )

    def dashboard_reset(self) -> bool:
        return self._run("dashboard_reset", extras={}, guard=True)

    def post_teleport_row(self, village_id: str, location_id: str, row_id: str) -> bool:
        try:
            zmod = importlib.import_module(f"core.servers.{self.server}.zones.rows")
            zones = getattr(zmod, "ZONES", {})
            templates = getattr(zmod, "TEMPLATES", {})
        except Exception as e:
            console.log(f"[rows] zones/templates load error: {e}")
            return False
        try:
            mod = importlib.import_module(
                f"core.servers.{self.server}.flows.rows.{village_id}.{location_id}.{row_id}"
            )
            flow = getattr(mod, "FLOW", None)
        except Exception as e:
            console.log(f"[rows] flow load error: {e}")
            return False
        if not flow:
            console.log("[rows] flow missing")
            return False

        ctx = FlowCtx(
            server=self.server,
            controller=self.controller,
            get_window=self.get_window,
            get_language=self.get_language,
            zones=zones,
            templates=templates,
            extras={"village_id": village_id, "location_id": location_id, "row_id": row_id},
        )
        execu = FlowOpExecutor(ctx)
        return run_flow(flow, execu)
