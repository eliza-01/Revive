# core/features/buff_after_respawn.py
# Баф после респавна: метод dashboard|npc, ждёт окончание, сигнализирует статус
import time
from typing import Callable, Optional

from core.servers.base_config import load_feature_config
from core.vision.matching import find_in_zone, click_center

BUFF_METHOD_DASHBOARD = "dashboard"
BUFF_METHOD_NPC = "npc"

class BuffAfterRespawnWorker:
    def __init__(self, controller, server: str, get_window: Callable[[], Optional[dict]], get_language: Callable[[], str], on_status: Callable[[str, Optional[bool]], None]):
        self.controller = controller
        self.server = server
        self._get_window = get_window
        self.get_language = get_language
        self._on_status = on_status
        self._cfg = load_feature_config(server, "buff")  # ZONES, TEMPLATES, SEQUENCE: dict per method
        self._mode = "profile"
        self._method = BUFF_METHOD_DASHBOARD

    def set_mode(self, mode: str):
        self._mode = (mode or "profile").lower()

    def set_method(self, method: str):
        m = (method or BUFF_METHOD_DASHBOARD).lower()
        if m not in (BUFF_METHOD_DASHBOARD, BUFF_METHOD_NPC):
            raise ValueError(f"unsupported buff method: {method}")
        self._method = m

    def run_once(self) -> bool:
        seq_map = self._cfg["SEQUENCE"]
        seq = seq_map.get(self._method, [])
        win = self._get_window() or {}
        for step in seq:
            action = step[0]
            if action == "key":
                key = step[1]
                self.controller.send(f"key:{key}")
            elif action == "wait_template":
                zone_key, tpl_key, timeout_ms = step[1], step[2], step[3]
                if not self._wait_template(win, zone_key, tpl_key, timeout_ms):
                    self._on_status(f"[buff] wait timeout: {tpl_key}", False)
                    return False
            elif action == "click_template":
                zone_key, tpl_key, timeout_ms = step[1], step[2], step[3]
                pt = self._wait_point(win, zone_key, tpl_key, timeout_ms)
                if not pt:
                    self._on_status(f"[buff] click timeout: {tpl_key}", False)
                    return False
                click_center(self.controller, pt)
            else:
                # future: dynamic selects by profile/mode
                pass
        self._on_status("[buff] complete", True)
        return True

    def _wait_template(self, win, zone_key, tpl_key, timeout_ms) -> bool:
        deadline = time.time() + max(0, timeout_ms)/1000.0
        zone = self._cfg["ZONES"].get(zone_key)
        tpl = self._cfg["TEMPLATES"].get(tpl_key)
        if not zone or not tpl:
            return False
        while time.time() < deadline:
            if find_in_zone(win, zone, tpl) is not None:
                return True
            time.sleep(0.05)
        return False

    def _wait_point(self, win, zone_key, tpl_key, timeout_ms):
        deadline = time.time() + max(0, timeout_ms)/1000.0
        zone = self._cfg["ZONES"].get(zone_key)
        tpl = self._cfg["TEMPLATES"].get(tpl_key)
        if not zone or not tpl:
            return None
        while time.time() < deadline:
            pt = find_in_zone(win, zone, tpl)
            if pt:
                return pt
            time.sleep(0.05)
        return None
