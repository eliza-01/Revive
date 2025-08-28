# core/engines/autofarm/service.py
from __future__ import annotations
from typing import Callable, List, Dict, Any

class AutoFarmService:
    """
    Режимы:
      - after_tp: ждать окончания приоритетных флоу, затем стартовать
      - manual: стартовать сразу по включению (без ожиданий)
    """
    def __init__(self, schedule: Callable[[Callable[[], None], int], None], log=print, on_start: Callable[[], None]=lambda: None):
        self.schedule = schedule
        self.log = log
        self.on_start = on_start

        self.mode = "after_tp"
        self.enabled = False
        self._armed = False           # «вооружён» к запуску после ТП
        self._tick_ms = 300

        self._pre_steps: List[tuple[str, Callable[[], bool]]] = []  # [(name, is_done)]
        self._cfg: Dict[str, Any] = {}

        self._poll()

    def set_mode(self, mode: str):
        self.mode = "after_tp" if mode == "after_tp" else "manual"

    def set_enabled(self, v: bool):
        self.enabled = bool(v)
        if self.enabled and self.mode == "manual":
            self._try_start()
        # в after_tp ждём notify_after_tp()

    def configure(self, cfg: Dict[str, Any]):
        self._cfg = dict(cfg or {})

    def register_pre_step(self, name: str, is_done: Callable[[], bool]):
        self._pre_steps.append((name, is_done))

    def clear_pre_steps(self):
        self._pre_steps.clear()

    def notify_after_tp(self):
        """Вызывать при событии 'стал жив' после ТП/смерти."""
        if self.enabled and self.mode == "after_tp":
            self._armed = True

    def _flows_ready(self) -> tuple[bool, str|None]:
        for name, done in self._pre_steps:
            try:
                if not bool(done()):
                    return False, name
            except Exception:
                return False, name
        return True, None

    def _try_start(self):
        ok, blocking = self._flows_ready()
        if not ok:
            self.log(f"[autofarm] wait: {blocking}")
            return False
        self.log("[autofarm] start")
        self.on_start()   # заглушка: тут вызов движка конкретного сервера
        self._armed = False
        return True

    def _poll(self):
        if self.enabled:
            if self.mode == "manual":
                # уже стартовали в set_enabled()
                pass
            elif self.mode == "after_tp" and self._armed:
                self._try_start()
        self.schedule(self._poll, self._tick_ms)
