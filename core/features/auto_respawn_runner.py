# core/features/auto_respawn_runner.py
# Только "встать". После успешного выполнения вызывает post_hook(window_info)
import threading
import time
from typing import Callable, Optional

from core.servers.base_config import load_feature_config
from core.vision.matching import find_in_zone, click_center

class AutoRespawnRunner:
    def __init__(
            self,
            controller,
            window_title: str,
            language: str,
            server: str,
            poll_interval: float = 0.5,
            debug: bool = False,
            window_provider: Optional[Callable[[], Optional[dict]]] = None,
    ):
        self.controller = controller
        self.window_title = window_title
        self.language = language
        self.server = server
        self.poll_interval = poll_interval
        self.debug = debug
        self._window_provider = window_provider or (lambda: None)

        self._post_hook = None
        self._running = False
        self._thr: Optional[threading.Thread] = None
        self._cfg = load_feature_config(self.server, "respawn")

    def set_language(self, lang: str):
        self.language = lang

    def set_server(self, server: str):
        self.server = server
        self._cfg = load_feature_config(server, "respawn")

    def set_post_respawn_hook(self, fn: Callable[[dict], None]):
        self._post_hook = fn

    def is_running(self) -> bool:
        return self._running

    def is_dead(self) -> bool:
        win = self._window_provider() or {}
        zone = self._cfg["ZONES"].get("death_banner")
        tpl = self._cfg["TEMPLATES"].get("death_banner")
        if not zone or not tpl:
            return False
        return find_in_zone(win, zone, tpl) is not None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                if self.is_dead():
                    if self.debug:
                        print("[respawn] dead → to village")
                    ok = self._perform_to_village()
                    if ok and self._post_hook:
                        win = self._window_provider() or {}
                        try:
                            self._post_hook(win)
                        except Exception as e:
                            print(f"[respawn] post hook error: {e}")
                    time.sleep(1.0)
                time.sleep(self.poll_interval)
            except Exception as e:
                print(f"[respawn] loop error: {e}")
                time.sleep(0.5)

    def _perform_to_village(self) -> bool:
        seq = self._cfg["SEQUENCE"]
        win = self._window_provider() or {}
        for step in seq:
            action = step[0]
            if action == "wait_template":
                zone_key, tpl_key, timeout_ms = step[1], step[2], step[3]
                if not self._wait_template(win, zone_key, tpl_key, timeout_ms):
                    return False
            elif action == "click_template":
                zone_key, tpl_key, timeout_ms = step[1], step[2], step[3]
                pt = self._wait_point(win, zone_key, tpl_key, timeout_ms)
                if not pt:
                    return False
                click_center(self.controller, pt)
            else:
                # игнорируем прочие действия в respawn-конфиге
                pass
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
