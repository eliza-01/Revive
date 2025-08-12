# core/features/buff_after_respawn.py
from __future__ import annotations
import importlib
import time
from typing import Callable, Optional, Dict, Tuple

from core.runtime.dashboard_guard import DASHBOARD_GUARD
from core.vision.matching.template_matcher import match_in_zone

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
        self.click_threshold = click_threshold
        self.debug = debug

        self._zones = {}
        self._templates = {}
        self._flow = None
        self._mode = BUFF_MODE_PROFILE
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
        win = self._get_window() or {}
        if not win:
            self._on_status("[buff] window missing", False)
            return False

        with DASHBOARD_GUARD.session():
            if self._flow:
                return self._run_flow(win)
            # fallback на дефолтный сценарий
            if not self._click_any(win, ("dashboard_tab", "dashboard_body"), "buffer_button", 2000):
                self._on_status("[buff] buffer button not found", False)
                return False
            if "buffer_init" in self._templates:
                self._wait_template(win, "dashboard_body", "buffer_init", 2000)
            mode_key = self._mode_tpl_key()
            if not self._click_in(win, "dashboard_body", mode_key, 2500):
                self._on_status(f"[buff] mode '{self._mode}' not found", False)
                return False
            if "buffer_restore_hp" in self._templates:
                self._click_in(win, "dashboard_body", "buffer_restore_hp", 1000)
            self._on_status("[buff] done", True)
            return True

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

    def _zone_ltrb(self, win: Dict, zone_decl):
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

    def _is_visible(self, win: Dict, zone_key: str, tpl_key_or_parts, thr: float) -> bool:
        zone = self._zones.get(zone_key)
        if not zone:
            return False
        ltrb = self._zone_ltrb(win, zone)
        parts = tpl_key_or_parts
        if isinstance(parts, str):
            parts = self._templates.get(parts, [])
        if not parts:
            return False
        return match_in_zone(win, ltrb, self.server, self._lang(), parts, thr) is not None

    def _wait_in(self, win: Dict, zone_key: str, tpl_key: str, timeout_ms: int, thr: float) -> bool:
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if self._is_visible(win, zone_key, tpl_key, thr):
                return True
            time.sleep(0.05)
        return False

    def _wait_while_visible(self, win: Dict, zone_key: str, tpl_key: str, timeout_ms: int, thr: float) -> bool:
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if not self._is_visible(win, zone_key, tpl_key, thr):
                return True
            time.sleep(0.1)
        return False

    def _wait_template(self, win: Dict, zone_key: str, tpl_key: str, timeout_ms: int, thr: float = None) -> bool:
        zone = self._zones.get(zone_key); tpl = self._templates.get(tpl_key)
        if not zone or not tpl:
            return False
        ltrb = self._zone_ltrb(win, zone)
        thr = self.click_threshold if thr is None else float(thr)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if match_in_zone(win, ltrb, self.server, self._lang(), tpl, thr):
                return True
            time.sleep(0.05)
        return False

    def _click_in(self, win: Dict, zone_key: str, tpl_key: str, timeout_ms: int, thr: float = None) -> bool:
        zone = self._zones.get(zone_key); tpl = self._templates.get(tpl_key)
        if not zone or not tpl:
            return False
        ltrb = self._zone_ltrb(win, zone)
        thr = self.click_threshold if thr is None else float(thr)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            pt = match_in_zone(win, ltrb, self.server, self._lang(), tpl, thr)
            if pt:
                self.controller.send(f"click:{pt[0]},{pt[1]}")
                return True
            time.sleep(0.05)
        return False

    def _click_any(self, win: Dict, zone_keys, tpl_key: str, timeout_ms: int, thr: float = None) -> bool:
        thr = self.click_threshold if thr is None else float(thr)
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            for zk in zone_keys:
                if self._click_in(win, zk, tpl_key, 1, thr):
                    return True
            time.sleep(0.05)
        return False

    # ---------- flow engine ----------
    def _run_flow(self, win: Dict) -> bool:
        total = len(self._flow) if self._flow else 0
        for idx, step in enumerate(self._flow, start=1):
            op = step.get("op")
            thr = float(step.get("thr", self.click_threshold))

            self._log(f"[buff][step {idx}/{total}] {op}: {step}")

            if op == "click_any":
                ok = self._click_any(win, tuple(step["zones"]), step["tpl"], int(step["timeout_ms"]), thr)
                self._log(f"[buff][step {idx}] result: {'OK' if ok else 'FAIL'}")
                if not ok:
                    self._on_status(f"[buff] click_any fail: {step}", False)
                    return False

            elif op == "wait":
                ok = self._wait_template(win, step["zone"], step["tpl"], int(step["timeout_ms"]), thr)
                self._log(f"[buff][step {idx}] result: {'OK' if ok else 'FAIL'}")
                if not ok:
                    self._on_status(f"[buff] wait fail: {step}", False)
                    return False

            elif op == "dashboard_is_locked":
                # Если блок виден, кликаем слева раз в 1с, пока блок не исчезнет.
                zone_key = step["zone"]
                tpl_key = step["tpl"]              # ожидаем ключ шаблона блокировки
                timeout_ms = int(step.get("timeout_ms", 8000))
                interval_s = float(step.get("probe_interval_s", 1.0))

                start_ts = time.time()
                next_probe = 0.0
                unlocked = False

                while (time.time() - start_ts) * 1000.0 < timeout_ms:
                    locked_now = self._is_visible(win, zone_key, tpl_key, thr)
                    if not locked_now:
                        unlocked = True
                        break

                    now = time.time()
                    if now >= next_probe:
                        self._log(f"[buff][step {idx}] locked → probe left-click")
                        self._probe_left_click()
                        next_probe = now + interval_s

                    time.sleep(0.08)

                self._log(f"[buff][step {idx}] unlocked: {'YES' if unlocked else 'NO'}")
                if not unlocked:
                    self._on_status("[buff] dashboard still locked", False)
                    return False

            elif op == "click_in":
                tpl_key = step["tpl"]
                if tpl_key == "{mode_key}":
                    tpl_key = self._mode_tpl_key()
                ok = self._click_in(win, step["zone"], tpl_key, int(step["timeout_ms"]), thr)
                self._log(f"[buff][step {idx}] result: {'OK' if ok else 'FAIL'}")
                if not ok:
                    self._on_status(f"[buff] click_in fail: {step}", False)
                    return False

            elif op == "optional_click":
                ok = self._click_in(win, step["zone"], step["tpl"], int(step.get("timeout_ms", 800)), thr)
                self._log(f"[buff][step {idx}] result: {'CLICKED' if ok else 'SKIP'}")

            elif op == "sleep":
                ms = int(step.get("ms", 50))
                self._log(f"[buff][step {idx}] sleeping {ms} ms")
                time.sleep(ms / 1000.0)

            elif op == "send_arduino":
                cmd = step.get("cmd", "")
                delay_ms = int(step.get("delay_ms", 100))
                self._log(f"[buff][step {idx}] send_arduino '{cmd}', delay {delay_ms} ms")
                self.controller.send(cmd)
                time.sleep(delay_ms / 1000.0)

            else:
                self._log(f"[buff][step {idx}] unknown op: {op}")
                self._on_status(f"[buff] unknown op: {op}", False)
                return False

        self._log("[buff] flow DONE")
        self._on_status("[buff] done", True)
        return True
