# core/features/auto_respawn_runner.py
# Автореспавн: только "встать" по шаблонам сервера. После успеха вызывает post_hook.
import importlib
import threading
import time
from typing import Callable, Optional, Dict, Tuple

from core.vision.matching.template_matcher import match_in_zone

class AutoRespawnRunner:
    def __init__(
            self,
            controller,
            window_title: str,
            language: str,
            server: str,
            poll_interval: float = 0.9,
            debug: bool = False,
            window_provider: Optional[Callable[[], Optional[dict]]] = None,
    ):
        self.controller = controller
        self.window_title = window_title
        self.language = language
        self.server = server
        self.poll_interval = poll_interval
        self.debug = debug
        self._get_window = window_provider or (lambda: None)

        self._post_hook: Optional[Callable[[dict], None]] = None
        self._running = False
        self._thr: Optional[threading.Thread] = None

        self._zones: Dict[str, Tuple[int, int, int, int]] = {}
        self._templates: Dict[str, list] = {}
        self._sequence = []
        self._load_config()

    # ---- public ----
    def set_language(self, lang: str):
        self.language = (lang or "rus").lower()

    def set_server(self, server: str):
        self.server = server
        self._load_config()

    def set_post_respawn_hook(self, fn: Callable[[dict], None]):
        self._post_hook = fn

    def is_running(self) -> bool:
        return self._running

    def is_dead(self) -> bool:
        # наличие баннера смерти — это wait_template первого шага
        win = self._get_window() or {}
        if not win:
            return False
        # ищем по первому wait_template в сценарии
        for step in self._sequence:
            if step[0] == "wait_template":
                zone_key, tpl_key, _timeout, thr = step[1], step[2], step[3], (step[4] if len(step) > 4 else 0.87)
                zone = self._zones.get(zone_key)
                tpl = self._templates.get(tpl_key)
                if not zone or not tpl:
                    return False
                return match_in_zone(win, zone, self.server, self.language, tpl, thr) is not None
        return False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._running = False

    # ---- internals ----
    def _load_config(self):
        try:
            mod = importlib.import_module(f"core.servers.{self.server}.zones.respawn")
            self._zones = getattr(mod, "ZONES", {})
            self._templates = getattr(mod, "TEMPLATES", {})
            self._sequence = getattr(mod, "SEQUENCE", [])
            if self.debug:
                print(f"[respawn] config loaded for {self.server}")
        except Exception as e:
            print(f"[respawn] config load error: {e}")
            self._zones, self._templates, self._sequence = {}, {}, []

    def _loop(self):
        while self._running:
            try:
                if self._try_respawn_cycle():
                    # дать времени UI стабилизироваться
                    time.sleep(0.8)
                    hook = self._post_hook
                    if hook:
                        win = self._get_window() or {}
                        try:
                            hook(win)
                        except Exception as e:
                            print(f"[respawn] post hook error: {e}")
                time.sleep(self.poll_interval)
            except Exception as e:
                print(f"[respawn] loop error: {e}")
                time.sleep(1)

    def _try_respawn_cycle(self) -> bool:
        win = self._get_window() or {}
        if not win or not self._sequence:
            return False

        # сначала проверяем, что действительно «мертв»
        first_wait = next((s for s in self._sequence if s[0] == "wait_template"), None)
        if not first_wait:
            return False
        zkey, tkey, timeout_ms, thr = first_wait[1], first_wait[2], first_wait[3], (first_wait[4] if len(first_wait) > 4 else 0.87)
        if not self._wait_template(win, zkey, tkey, timeout_ms, thr):
            return False

        # выполняем шаги
        for step in self._sequence:
            kind = step[0]
            if kind == "wait_template":
                zkey, tkey, timeout_ms, thr = step[1], step[2], step[3], (step[4] if len(step) > 4 else 0.87)
                if not self._wait_template(win, zkey, tkey, timeout_ms, thr):
                    if self.debug:
                        print(f"[respawn] wait timeout: {zkey}/{tkey}")
                    return False
            elif kind == "click_template":
                zkey, tkey, timeout_ms, thr = step[1], step[2], step[3], (step[4] if len(step) > 4 else 0.87)
                pt = self._wait_point(win, zkey, tkey, timeout_ms, thr)
                if not pt:
                    if self.debug:
                        print(f"[respawn] click timeout: {zkey}/{tkey}")
                    return False
                self.controller.send(f"click:{pt[0]},{pt[1]}")
                time.sleep(0.08)
            # игнорируем прочие типы

        if self.debug:
            print("[respawn] done")
        return True

    def _wait_template(self, win: Dict, zkey: str, tkey: str, timeout_ms: int, thr: float) -> bool:
        deadline = time.time() + max(0, timeout_ms) / 1000.0
        zone = self._zones.get(zkey); tpl = self._templates.get(tkey)
        if not zone or not tpl:
            return False
        while time.time() < deadline:
            if match_in_zone(win, zone, self.server, self.language, tpl, thr):
                return True
            time.sleep(0.05)
        return False

    def _wait_point(self, win: Dict, zkey: str, tkey: str, timeout_ms: int, thr: float):
        deadline = time.time() + max(0, timeout_ms) / 1000.0
        zone = self._zones.get(zkey); tpl = self._templates.get(tkey)
        if not zone or not tpl:
            return None
        while time.time() < deadline:
            pt = match_in_zone(win, zone, self.server, self.language, tpl, thr)
            if pt:
                return pt
            time.sleep(0.05)
        return None
