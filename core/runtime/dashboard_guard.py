# core/runtime/dashboard_guard.py
import threading
import time
from contextlib import contextmanager

class DashboardGuard:
    """
    Общий сериализатор работ с dashboard (баф, телепорт и т.п.).
    Любая операция, открывающая/использующая dashboard, должна:
      with DASHBOARD_GUARD.session():
          ... действия ...
    Или вручную: wait_free(); acquire(); ...; release()
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._busy = threading.Event()  # True → занят

    def is_busy(self) -> bool:
        return self._busy.is_set()

    def wait_free(self, timeout: float = None) -> bool:
        if not self._busy.is_set():
            return True
        deadline = None if timeout is None else time.time() + max(0.0, timeout)
        while self._busy.is_set():
            if deadline is not None and time.time() >= deadline:
                return False
            time.sleep(0.03)
        return True

    def acquire(self):
        self._lock.acquire()
        self._busy.set()

    def release(self):
        self._busy.clear()
        try:
            self._lock.release()
        except Exception:
            pass

    @contextmanager
    def session(self):
        self.acquire()
        try:
            yield
        finally:
            self.release()

DASHBOARD_GUARD = DashboardGuard()
