# _archive/core/runtime/poller.py
import threading
import time

class RepeaterThread:
    def __init__(self, fn, interval: float, debug: bool = False):
        self.fn = fn
        self.interval = max(0.05, float(interval))
        self.debug = debug
        self._running = False
        self._thr = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def _loop(self):
        while self._running:
            try:
                self.fn()
            except Exception as e:
                print(f"[poller] fn error: {e}")
            time.sleep(self.interval)
