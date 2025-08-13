# =========================
# File: core/features/tp_after_respawn.py
# Flow-only TP worker (dashboard/gatekeeper). With per-step logging.
# =========================
from __future__ import annotations
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
            check_is_dead: Optional[Callable[[], bool]] = None,
            wait_alive_timeout_s: float = 1.0,
    ):
        self.controller = controller
        self.window = window_info
        self.get_language = get_language
        self._on_status = on_status

        self.server = "l2mad"
        self._zones: Dict[str, object] = {}
        self._templates: Dict[str, list] = {}
        self._flow = None
        self._load_cfg()

        self._method = TP_METHOD_DASHBOARD
        self._category_id: Optional[str] = None
        self._location_id: Optional[str] = None

        self._check_is_dead = check_is_dead
        self._wait_alive_timeout_s = float(wait_alive_timeout_s)

    # ---------- public ----------
    def configure(self, category_id: str, location_id: str, method: str = TP_METHOD_DASHBOARD):
        self._category_id = category_id
        self._location_id = location_id
        self._method = (method or TP_METHOD_DASHBOARD).lower()

    def set_method(self, method: str):
        self._method = (method or TP_METHOD_DASHBOARD).lower()

    def start(self):
        pass

    def stop(self):
        pass

    def teleport_now(self, category_id: str, location_id: str, method: Optional[str] = None) -> bool:
        if method:
            self._method = (method or TP_METHOD_DASHBOARD).lower()
        self._category_id = category_id
        self._location_id = location_id

        if not self._wait_until_alive(timeout_s=self._wait_alive_timeout_s):
            self._on_status("[tp] still dead, abort", False)
            print("[tp] guard: still dead → abort")
            return False

        if self._method == TP_METHOD_DASHBOARD:
            DASHBOARD_GUARD.wait_free(timeout=10.0)
            with DASHBOARD_GUARD.session():
                return self._run_flow(self.window or {})
        elif self._method == TP_METHOD_GATEKEEPER:
            return self._tp_via_gatekeeper()
        else:
            self._on_status(f"[tp] unknown method: {self._method}", False)
            return False

    # ---------- internals ----------
    def _log(self, msg: str) -> None:
        try:
            print(msg)
        except Exception:
            pass

    def _is_dead(self) -> bool:
        try:
            return bool(self._check_is_dead()) if callable(self._check_is_dead) else False
        except Exception:
            return False

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
            time.sleep(5)
        return False

    def _probe_b(self):
        try:
            self.controller.send("b")
        except Exception:
            pass
    def _probe_left_click(self):
        try:
            self.controller.send("l")  # левый клик
        except Exception:
            pass

    def _load_cfg(self):
        try:
            mod = importlib.import_module(f"core.servers.{self.server}.zones.tp")
            self._zones = getattr(mod, "ZONES", {})
            self._templates = getattr(mod, "TEMPLATES", {})
        except Exception as e:
            self._on_status(f"[tp] cfg load error: {e}", False)
            self._zones, self._templates = {}, {}

        try:
            flow_mod = importlib.import_module(f"core.servers.{self.server}.flows.tp")
            self._flow = getattr(flow_mod, "FLOW", None)
        except Exception:
            self._flow = None

        self._log(f"[tp] cfg loaded for {self.server}. flow={'yes' if self._flow else 'no'}")
        # alias: accept "dashboard_blocked" as "dashboard_is_locked"
        if "dashboard_is_locked" not in self._templates and "dashboard_blocked" in self._templates:
            self._templates["dashboard_is_locked"] = self._templates["dashboard_blocked"]

    def _lang(self) -> str:
        try:
            return (self.get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _zone_ltrb(self, zone_decl) -> Tuple[int, int, int, int]:
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
        return (0, 0, int((win or {}).get("width", 0)), int((win or {}).get("height", 0)))

    def _wait_template(self, zone_key: str, tpl_key: str, timeout_ms: int, thr: float) -> bool:
        zone = self._zones.get(zone_key); tpl = self._templates.get(tpl_key)
        if not zone or not tpl:
            return False
        ltrb = self._zone_ltrb(zone)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if match_in_zone(self.window, ltrb, self.server, self._lang(), tpl, thr):
                return True
            time.sleep(0.05)
        return False

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

    def _click_in(self, zone_key: str, tpl_key_or_parts, timeout_ms: int, thr: float) -> bool:
        zone = self._zones.get(zone_key)
        if not zone:
            return False
        tpl_parts = tpl_key_or_parts
        if isinstance(tpl_parts, str):
            tpl_parts = self._templates.get(tpl_parts, [])
        if not tpl_parts:
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

    def _click_any(self, zone_keys, tpl_key: str, timeout_ms: int, thr: float) -> bool:
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            for zk in zone_keys:
                if self._click_in(zk, tpl_key, 1, thr):
                    return True
            time.sleep(0.05)
        return False

    # ---------- FLOW engine ----------
    def _run_flow(self, win: Dict) -> bool:
        if not self._flow:
            self._on_status("[tp] flow missing", False)
            return False
        if not (self.window and self._category_id and self._location_id):
            self._on_status("[tp] missing window/category/location", False)
            return False

        total = len(self._flow)
        for idx, step in enumerate(self._flow, start=1):
            op = step.get("op")
            thr = float(step.get("thr", 0.87))
            self._log(f"[tp][step {idx}/{total}] {op}: {step}")

            if op == "click_any":
                ok = self._click_any(tuple(step["zones"]), step["tpl"], int(step["timeout_ms"]), thr)
                self._log(f"[tp][step {idx}] result: {'OK' if ok else 'FAIL'}")
                if not ok:
                    self._on_status(f"[tp] click_any fail: {step}", False)
                    return False

            elif op == "wait":
                ok = self._wait_template(step["zone"], step["tpl"], int(step["timeout_ms"]), thr)
                self._log(f"[tp][step {idx}] result: {'OK' if ok else 'FAIL'}")
                if not ok:
                    self._on_status(f"[tp] wait fail: {step}", False)
                    return False

            elif op == "dashboard_is_locked":
                zone_key = step["zone"]
                tpl_key = step["tpl"]
                timeout_ms = int(step.get("timeout_ms", 8000))
                interval_s = float(step.get("probe_interval_s", 1.0))

                if isinstance(tpl_key, str) and not self._templates.get(tpl_key) and self._templates.get("dashboard_blocked"):
                    self._templates["dashboard_is_locked"] = self._templates["dashboard_blocked"]

                start_ts = time.time()
                next_probe = 0.0
                unlocked = False

                while (time.time() - start_ts) * 1000.0 < timeout_ms:
                    if self._is_dead():
                        break

                    locked_now = self._is_visible(zone_key, tpl_key, thr)
                    if not locked_now:
                        unlocked = True
                        break

                    now = time.time()
                    if now >= next_probe:
                        self._log(f"[tp][step {idx}] locked → probe left-click")
                        self._probe_left_click()
                        next_probe = now + interval_s

                    time.sleep(0.08)

                self._log(f"[tp][step {idx}] unlocked: {'YES' if unlocked else 'NO'}")
                if not unlocked:
                    self._on_status("[tp] dashboard still locked", False)
                    return False

            elif op == "click_in":
                ok = self._click_in(step["zone"], step["tpl"], int(step["timeout_ms"]), thr)
                self._log(f"[tp][step {idx}] result: {'OK' if ok else 'FAIL'}")
                if not ok:
                    self._on_status(f"[tp] click_in fail: {step}", False)
                    return False

            elif op == "optional_click":
                ok = self._click_in(step["zone"], step["tpl"], int(step.get("timeout_ms", 800)), thr)
                self._log(f"[tp][step {idx}] result: {'CLICKED' if ok else 'SKIP'}")

            elif op == "click_village":
                lang = self._lang()
                village_png = f"{self._category_id}.png"
                ok_res = l2mad_resolver.teleport_location(lang, self._category_id, village_png)
                self._log(f"[tp][step {idx}] resolve village '{self._category_id}' → {'OK' if ok_res else 'FAIL'}")
                if not ok_res:
                    self._on_status(f"[tp] village template missing: {self._category_id}", False)
                    return False
                parts = ["dashboard", "teleport", "villages", self._category_id, village_png]
                ok = self._click_in("dashboard_body", parts, int(step.get("timeout_ms", 2500)), float(step.get("thr", 0.88)))
                self._log(f"[tp][step {idx}] click village → {'OK' if ok else 'FAIL'}")
                if not ok:
                    self._on_status(f"[tp] village not found: {self._category_id}", False)
                    return False

            elif op == "click_location":
                lang = self._lang()
                loc_png = f"{self._location_id}.png"
                ok_res = l2mad_resolver.teleport_location(lang, self._category_id, loc_png)
                self._log(f"[tp][step {idx}] resolve location '{self._category_id}/{self._location_id}' → {'OK' if ok_res else 'FAIL'}")
                if not ok_res:
                    self._on_status(f"[tp] location template missing: {self._category_id}/{self._location_id}", False)
                    return False
                parts = ["dashboard", "teleport", "villages", self._category_id, loc_png]
                ok = self._click_in("dashboard_body", parts, int(step.get("timeout_ms", 2500)), float(step.get("thr", 0.88)))
                self._log(f"[tp][step {idx}] click location → {'OK' if ok else 'FAIL'}")
                if not ok:
                    self._on_status(f"[tp] location not found: {self._location_id}", False)
                    return False

            elif op == "sleep":
                ms = int(step.get("ms", 50))
                self._log(f"[tp][step {idx}] sleeping {ms} ms")
                time.sleep(ms / 1000.0)

            elif op == "send_arduino":
                cmd = step.get("cmd", "")
                delay_ms = int(step.get("delay_ms", 100))
                self._log(f"[tp][step {idx}] send_arduino '{cmd}', delay {delay_ms} ms")
                self.controller.send(cmd)
                time.sleep(delay_ms / 1000.0)

            else:
                self._log(f"[tp][step {idx}] unknown op: {op}")
                self._on_status(f"[tp] unknown op: {op}", False)
                return False

        self._log("[tp] flow DONE")
        self._on_status("[tp] dashboard ok", True)
        return True

    def _tp_via_gatekeeper(self) -> bool:
        self._on_status("[tp] gatekeeper method not implemented yet", False)
        return False
