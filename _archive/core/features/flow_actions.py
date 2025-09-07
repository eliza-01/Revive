# _archive/core/features/flow_actions.py
from __future__ import annotations
import importlib
from typing import Callable, Optional, Dict, Any

from _archive.core.runtime.dashboard_guard import DASHBOARD_GUARD
from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow
from core.servers.l2mad.templates import resolver as l2mad_resolver

class FlowActions:
    def __init__(
            self,
            controller,
            server: str,
            get_window: Callable[[], Optional[Dict]],
            get_language: Callable[[], str],
            on_status=lambda *_: None,
            logger=print,
    ):
        self.controller = controller
        self.server = server
        self.get_window = get_window
        self.get_language = get_language
        self.on_status = on_status
        self.log = logger

    def _load(self, feature: str):
        zones = templates = flow = None
        try:
            zmod = importlib.import_module(f"core.servers.{self.server}.zones.{feature}")
            zones = getattr(zmod, "ZONES", {})
            templates = getattr(zmod, "TEMPLATES", {})
        except Exception as e:
            self.on_status(f"[flow] zones/templates load error: {e}", False)
            zones, templates = {}, {}
        try:
            fmod = importlib.import_module(f"core.servers.{self.server}.flows.{feature}")
            flow = getattr(fmod, "FLOW", None)
        except Exception:
            flow = None
        return zones, templates, flow

    def _run(self, feature: str, extras: Dict[str, Any] = None, guard: bool = False) -> bool:
        zones, templates, flow = self._load(feature)
        if not flow:
            self.on_status(f"[{feature}] flow missing", False)
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
        execu = FlowOpExecutor(ctx, on_status=self.on_status, logger=self.log)
        if guard:
            DASHBOARD_GUARD.wait_free(timeout=10.0)
            with DASHBOARD_GUARD.session():
                return run_flow(flow, execu)
        return run_flow(flow, execu)

    # public APIs
    def buff(self, mode_key_provider) -> bool:
        return self._run("buff", extras={"mode_key_provider": mode_key_provider}, guard=True)

    def tp_dashboard(self, category_id: str, location_id: str) -> bool:
        return self._run(
            "tp",
            extras={"resolver": l2mad_resolver.resolve, "category_id": category_id, "location_id": location_id},
            guard=True,
        )

    def dashboard_reset(self) -> bool:
        return self._run("dashboard_reset", extras={}, guard=True)

    def post_tp_row(self, village_id: str, location_id: str, row_id: str) -> bool:
        # зоны/шаблоны общие для rows
        try:
            zmod = importlib.import_module(f"core.servers.{self.server}.zones.rows")
            zones = getattr(zmod, "ZONES", {})
            templates = getattr(zmod, "TEMPLATES", {})
        except Exception as e:
            self.on_status(f"[rows] zones/templates load error: {e}", False)
            return False
        # сам flow берём из файлов локации
        try:
            mod = importlib.import_module(
                f"core.servers.{self.server}.flows.rows.{village_id}.{location_id}.{row_id}"
            )
            flow = getattr(mod, "FLOW", None)
        except Exception as e:
            self.on_status(f"[rows] flow load error: {e}", False)
            return False
        if not flow:
            self.on_status("[rows] flow missing", False)
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
        execu = FlowOpExecutor(ctx, on_status=self.on_status, logger=self.log)
        return run_flow(flow, execu)
