from __future__ import annotations
import time
import importlib
from typing import Callable, Optional, Dict

from core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"


class TPAfterDeathWorker:
    """
    Телепорт после смерти с выбором метода:
      - flows: core.servers.<server>.flows.tp_<method>  (fallback: flows.tp)
      - zones: core.servers.<server>.zones.tp_<method>  (fallback: zones.tp)
    Для L2MAD сервер зашит как 'l2mad' (как и было до ветвления).
    """
    def __init__(
        self,
        controller,
        window_info: Optional[dict],
        get_language: Callable[[], str],
        on_status: Callable[[str, Optional[bool]], None] = lambda *_: None,
        check_is_dead: Optional[Callable[[], bool]] = None,
        wait_alive_timeout_s: float = 1.0,
    ):
        self._controller = controller
        self._window_info = window_info
        self._get_language = get_language
        self._on_status = on_status
        self._check_is_dead = check_is_dead
        self._wait_alive_timeout_s = float(wait_alive_timeout_s)

        self._server = "l2mad"  # как в текущей версии (UI локации тоже из l2mad)
        self._method = TP_METHOD_DASHBOARD
        self._category_id: Optional[str] = None
        self._location_id: Optional[str] = None

    # UI дергает это при смене метода
    def set_method(self, method: str):
        m = (method or TP_METHOD_DASHBOARD).lower()
        self._method = m if m in (TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER) else TP_METHOD_DASHBOARD

    # UI вызывает перед телепортом
    def configure(self, category_id: str, location_id: str, method: str = TP_METHOD_DASHBOARD):
        self._category_id = category_id or ""
        self._location_id = location_id or ""
        self.set_method(method)

    # чтобы UI мог обновлять окно перед запуском
    @property
    def window(self) -> Optional[dict]:
        return self._window_info

    @window.setter
    def window(self, win: Optional[dict]):
        self._window_info = win

    def _wait_until_alive(self, timeout_s: float) -> bool:
        if not callable(self._check_is_dead):
            return True
        deadline = time.time() + float(timeout_s)
        while time.time() < deadline:
            try:
                if not self._check_is_dead():
                    return True
            except Exception:
                return True
            time.sleep(0.25)
        return True  # мягко: не блокируем, просто продолжаем

    def teleport_now(self, category_id: str, location_id: str, method: Optional[str] = None) -> bool:
        cat = (category_id or self._category_id or "").strip()
        loc = (location_id or self._location_id or "").strip()
        if method:
            self.set_method(method)

        if not (cat and loc):
            self._on_status("[tp] destination not selected", False)
            return False

        self._wait_until_alive(self._wait_alive_timeout_s)

        server = self._server

        # ---- resolver (для click_village / click_location) ----
        try:
            # ВНИМАНИЕ: у L2MAD resolver лежит в templates/
            rmod = importlib.import_module(f"core.servers.{server}.templates.resolver")
            resolver = getattr(rmod, "resolve")
        except Exception as e:
            self._on_status(f"[tp] resolver load error: {e}", False)
            return False

        # ---- flows ----
        try:
            try:
                fmod = importlib.import_module(f"core.servers.{server}.flows.tp_{self._method}")
            except Exception:
                fmod = importlib.import_module(f"core.servers.{server}.flows.tp")
            flow = getattr(fmod, "FLOW", [])
        except Exception as e:
            self._on_status(f"[tp] flow load error: {e}", False)
            return False

        # ---- zones/templates ----
        try:
            try:
                zmod = importlib.import_module(f"core.servers.{server}.zones.tp_{self._method}")
            except Exception:
                zmod = importlib.import_module(f"core.servers.{server}.zones.tp")
            zones = getattr(zmod, "ZONES", {})
            templates = getattr(zmod, "TEMPLATES", {})
        except Exception as e:
            self._on_status(f"[tp] zones load error: {e}", False)
            return False

        ctx = FlowCtx(
            server=server,
            controller=self._controller,
            get_window=lambda: self._window_info,
            get_language=self._get_language,
            zones=zones,
            templates=templates,
            extras={
                "resolver": resolver,
                "category_id": cat,
                "location_id": loc,
            },
        )
        execu = FlowOpExecutor(ctx, on_status=self._on_status, logger=lambda m: print(m))
        ok = run_flow(flow, execu)
        self._on_status(f"[tp] run → {ok}", ok)
        return bool(ok)
