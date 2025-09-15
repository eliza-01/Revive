# _archive/core/features/restart_manager.py
from __future__ import annotations
import importlib
import time
from typing import Callable, Optional

from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow
from core.logging import console


class RestartManager:
    def __init__(
        self,
        *,
        controller,
        get_server: Callable[[], str],
        get_window: Callable[[], Optional[dict]],
        get_language: Callable[[], str],
        watcher,
        account_getter: Callable[[], dict],  # {"login","password","pin"}
        max_restart_attempts: int = 3,
        retry_delay_s: float = 1.0,
    ):
        self.controller = controller
        self.get_server = get_server
        self.get_window = get_window
        self.get_language = get_language
        self.watcher = watcher
        self.account_getter = account_getter
        self._max_restart_attempts = int(max_restart_attempts)
        self._retry_delay_s = float(retry_delay_s)

    def _extras(self) -> dict:
        acc = dict(self.account_getter() or {"login": "", "password": "", "pin": ""})
        return {
            "account": acc,
            "account_login": acc.get("login", ""),
            "account_password": acc.get("password", ""),
            "account_pin": acc.get("pin", ""),
        }

    def run_dashboard_reset(self) -> bool:
        server = self.get_server()
        try:
            flow_mod = importlib.import_module(f"core.servers.{server}.flows.dashboard_reset")
            flow = getattr(flow_mod, "FLOW", [])
        except Exception as e:
            console.log(f"[reset] load flow error: {e}")
            return False

        try:
            zones_mod = importlib.import_module(f"core.servers.{server}.zones.teleport_dashboard")
        except Exception:
            zones_mod = importlib.import_module(f"core.servers.{server}.zones.teleport_dashboard")

        zones = getattr(zones_mod, "ZONES", {})
        templates = getattr(zones_mod, "TEMPLATES", {})

        ctx = FlowCtx(
            server=server,
            controller=self.controller,
            get_window=self.get_window,
            get_language=self.get_language,
            zones=zones,
            templates=templates,
            extras=self._extras(),
        )
        execu = FlowOpExecutor(ctx)
        ok = run_flow(flow, execu)
        console.log(f"[reset] dashboard_reset → {ok}")
        return bool(ok)

    def restart_account(self) -> bool:
        """Полный рестарт аккаунта с многократными попытками (лог только в консоль)."""
        server = self.get_server()
        console.log("[reset] restart_account …")

        ok = False
        was_running = False

        try:
            was_running = self.watcher.is_running()
            if was_running:
                self.watcher.stop()
                console.log("[reset] watcher OFF during restart")

            attempts = 0
            while attempts < self._max_restart_attempts and not ok:
                attempts += 1
                console.log(f"[restart] attempt {attempts}/{self._max_restart_attempts}")

                try:
                    flow_mod = importlib.import_module(f"core.servers.{server}.flows.restart")
                    flow = getattr(flow_mod, "FLOW", [])
                except Exception as e:
                    console.log(f"[restart] load flow error: {e}")
                    flow = []

                try:
                    zones_mod = importlib.import_module(f"core.servers.{server}.zones.restart")
                    zones = getattr(zones_mod, "ZONES", {})
                    templates = getattr(zones_mod, "TEMPLATES", {})
                except Exception as e:
                    console.log(f"[restart] load zones error: {e}")
                    zones, templates = {}, {}

                ctx = FlowCtx(
                    server=server,
                    controller=self.controller,
                    get_window=self.get_window,
                    get_language=self.get_language,
                    zones=zones,
                    templates=templates,
                    extras=self._extras(),
                )
                execu = FlowOpExecutor(ctx)
                ok = run_flow(flow, execu)
                console.log(f"[restart] flow → {ok}")

                if not ok and attempts < self._max_restart_attempts:
                    try:
                        self.run_dashboard_reset()
                    except Exception as e:
                        console.log(f"[restart] fallback dashboard_reset error: {e}")
                    time.sleep(self._retry_delay_s)
        finally:
            try:
                self.watcher._alive_flag = None
            except Exception:
                pass

            if was_running and ok:
                self.watcher.start()
                console.log("[reset] watcher ON after restart")
            elif was_running and not ok:
                console.log("[reset] watcher remains OFF (restart failed)")

        return bool(ok)
