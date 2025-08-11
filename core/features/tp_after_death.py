# core/features/tp_after_death.py
import threading
import time
from typing import Callable, Optional

TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"

class TPAfterDeathWorker:
    def __init__(self, controller, window_info, get_language: Callable[[], str], on_status: Callable[[str, Optional[bool]], None]):
        self.controller = controller
        self.window = window_info
        self.get_language = get_language
        self._on_status = on_status
        self._cat = ""
        self._loc = ""
        self._method = TP_METHOD_DASHBOARD
        self._running = False
        self._thr: Optional[threading.Thread] = None
        self.check_is_dead: Callable[[], bool] = lambda: False
        self.focus_game_window: Callable[[], None] = lambda: None

    def configure(self, category_id: str, location_id: str, method: Optional[str] = None):
        self._cat = category_id or ""
        self._loc = location_id or ""
        if method:
            self.set_method(method)

    def set_method(self, method: str):
        m = (method or TP_METHOD_DASHBOARD).lower()
        if m not in (TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER):
            raise ValueError(f"Unsupported TP method: {method}")
        self._method = m

    def get_method(self) -> str:
        return self._method

    def start(self):
        if self._running:
            return
        self._running = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._running = False

    def validate_templates(self, category_id: str, location_id: str, method: Optional[str] = None):
        return True

    def teleport_now(self, category_id: str, location_id: str, method: Optional[str] = None) -> bool:
        if method:
            self.set_method(method)
        if self._method == TP_METHOD_DASHBOARD:
            return self._tp_via_dashboard(category_id, location_id)
        return self._tp_via_gatekeeper(category_id, location_id)

    def _tp_via_dashboard(self, category_id: str, location_id: str) -> bool:
        self._on_status(f"[dash] open dashboard", None)
        time.sleep(0.1)
        self._on_status(f"[dash] select '{category_id}'", None)
        time.sleep(0.1)
        self._on_status(f"[dash] click '{location_id}'", None)
        time.sleep(0.1)
        self._on_status(f"ТП через dashboard: {category_id} / {location_id}", True)
        print(f"[tp] dashboard → {category_id}/{location_id}")
        return True

    def _tp_via_gatekeeper(self, category_id: str, location_id: str) -> bool:
        self._on_status("[gk] go to gatekeeper", None)
        time.sleep(0.1)
        self._on_status("[gk] open dialog", None)
        time.sleep(0.1)
        self._on_status(f"[gk] choose '{category_id}' → '{location_id}'", None)
        time.sleep(0.1)
        self._on_status(f"ТП через gatekeeper: {category_id} / {location_id}", True)
        print(f"[tp] gatekeeper → {category_id}/{location_id}")
        return True

    def _loop(self):
        while self._running:
            try:
                self._on_status("Ожидание события смерти...", None)
                time.sleep(2.0)
            except Exception as e:
                self._on_status(f"Ошибка воркера: {e}", False)
                time.sleep(1.0)
