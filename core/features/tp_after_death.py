# core/features/tp_after_death.py  # патч: ожидание окончания бафа через DASHBOARD_GUARD
import importlib
import time
from typing import Callable, Optional, Dict, Tuple

from core.runtime.dashboard_guard import DASHBOARD_GUARD
from core.vision.matching.template_matcher import match_in_zone
from core.servers.l2mad.templates import resolver as l2mad_resolver

TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"

class TPAfterDeathWorker:
    def __init__(
            self,
            controller,
            window_info: Optional[dict],
            get_language: Callable[[], str],
            on_status: Callable[[str, Optional[bool]], None] = lambda *_: None,
    ):
        self.controller = controller
        self.window = window_info
        self.get_language = get_language
        self._on_status = on_status

        self.server = "l2mad"
        self._zones = {}
        self._templates = {}
        self._load_cfg()

        self._method = TP_METHOD_DASHBOARD
        self._category_id: Optional[str] = None
        self._location_id: Optional[str] = None

    def configure(self, category_id: str, location_id: str, method: str = TP_METHOD_DASHBOARD):
        self._category_id = category_id
        self._location_id = location_id
        self._method = (method or TP_METHOD_DASHBOARD).lower()

    def set_method(self, method: str):
        self._method = (method or TP_METHOD_DASHBOARD).lower()

    def start(self):  # совместимость
        pass

    def stop(self):   # совместимость
        pass

    def teleport_now(self, category_id: str, location_id: str, method: Optional[str] = None) -> bool:
        if method:
            self._method = method
        self._category_id = category_id
        self._location_id = location_id
        if self._method == TP_METHOD_DASHBOARD:
            return self._tp_via_dashboard_serialized()
        elif self._method == TP_METHOD_GATEKEEPER:
            return self._tp_via_gatekeeper()
        else:
            self._on_status(f"[tp] unknown method: {self._method}", False)
            return False

    # ===== Internals =====
    def _load_cfg(self):
        try:
            mod = importlib.import_module(f"core.servers.{self.server}.zones.tp")
            self._zones = getattr(mod, "ZONES", {})
            self._templates = getattr(mod, "TEMPLATES", {})
        except Exception as e:
            self._on_status(f"[tp] cfg load error: {e}", False)
            self._zones, self._templates = {}, {}

    def _lang(self) -> str:
        try:
            return (self.get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _tp_via_dashboard_serialized(self) -> bool:
        # Ждём, пока баф закончит работу с dashboard
        DASHBOARD_GUARD.wait_free(timeout=10.0)
        # Бронируем панель под телепорт, чтобы баф не влез меж кликов
        with DASHBOARD_GUARD.session():
            return self._tp_via_dashboard_locked()

    def _tp_via_dashboard_locked(self) -> bool:
        if not (self.window and self._category_id and self._location_id):
            self._on_status("[tp] missing window/category/location", False)
            return False

        lang = self._lang()

        # открыть таб ТП
        if not self._click_any(("dashboard_tab", "dashboard_body"), "tab_tp", 1500, 0.87):
            self._on_status("[tp] teleport tab not found", False)
            return False

        # выбрать деревню
        village_png = f"{self._category_id}.png"
        if not l2mad_resolver.teleport_location(lang, self._category_id, village_png):
            self._on_status(f"[tp] village template missing: {self._category_id}", False)
            return False
        if not self._click_in("dashboard_body", ["dashboard", "teleport", "villages", self._category_id, village_png], 2500, 0.88):
            self._on_status(f"[tp] village not found: {self._category_id}", False)
            return False

        # выбрать локацию
        loc_png = f"{self._location_id}.png"
        if not l2mad_resolver.teleport_location(lang, self._category_id, loc_png):
            self._on_status(f"[tp] location template missing: {self._category_id}/{self._location_id}", False)
            return False
        if not self._click_in("dashboard_body", ["dashboard", "teleport", "villages", self._category_id, loc_png], 2500, 0.88):
            self._on_status(f"[tp] location not found: {self._location_id}", False)
            return False

        # подтверждение если требуется
        if "confirm" in self._templates:
            self._click_in("confirm", self._templates["confirm"], 1500, 0.90)

        self._on_status("[tp] dashboard ok", True)
        return True

    # ---- helpers over matcher ----
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

    def _click_in(self, zone_key: str, tpl_parts, timeout_ms: int, thr: float):
        zone = self._zones.get(zone_key)
        if not zone:
            return False
        ltrb = self._zone_ltrb(zone)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            pt = match_in_zone(self.window, ltrb, self.server, self._lang(), tpl_parts, thr)
            if pt:
                self.controller.send(f"click:{pt[0]},{pt[1]}")
                time.sleep(0.08)
                return True
            time.sleep(0.05)
        return False

    def _click_any(self, zone_keys, tpl_key: str, timeout_ms: int, thr: float):
        tpl = self._templates.get(tpl_key, [])
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            for zk in zone_keys:
                if self._click_in(zk, tpl, 1, thr):
                    return True
            time.sleep(0.05)
        return False

    def _tp_via_gatekeeper(self) -> bool:
        self._on_status("[tp] gatekeeper method not implemented yet", False)
        return False
