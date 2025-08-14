# core/runtime/cycle_flow.py
from __future__ import annotations
import threading
import time
from typing import Callable, Optional, Protocol, List, Dict, Any, Tuple

class Task(Protocol):
    name: str
    priority: int  # меньше = важнее
    def is_ready(self) -> bool: ...
    def run(self) -> bool: ...   # блокирующий запуск; True=успех

class CycleFlow:
    """
    Диспетчер действий: Баф → Макросы → ТП → Навигация и т.д.
    Выполняет только одну задачу за раз, по приоритету и готовности.
    """

    def __init__(self, poll_interval: float = 0.1):
        self._tasks: List[Task] = []
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._poll = float(poll_interval)
        self._on_status: Callable[[str, Optional[bool]], None] = lambda *_: None

    def set_on_status(self, cb: Callable[[str, Optional[bool]], None]) -> None:
        self._on_status = cb or (lambda *_: None)

    def add_task(self, task: Task) -> None:
        with self._lock:
            self._tasks.append(task)
            self._tasks.sort(key=lambda t: t.priority)

    def remove_task(self, name: str) -> None:
        with self._lock:
            self._tasks = [t for t in self._tasks if getattr(t, "name", "") != name]

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        th = self._thread
        if th:
            th.join(timeout=1.0)
        self._thread = None

    # ---- internals ----
    def _loop(self):
        while self._running:
            task = self._pick_next_ready()
            if task:
                self._exec(task)
            else:
                time.sleep(self._poll)

    def _pick_next_ready(self) -> Optional[Task]:
        with self._lock:
            for t in self._tasks:
                try:
                    if t.is_ready():
                        return t
                except Exception:
                    # не даём упасть лупу
                    pass
        return None

    def _exec(self, task: Task):
        name = getattr(task, "name", "task")
        try:
            self._on_status(f"[flow] start {name}", None)
            ok = bool(task.run())
            self._on_status(f"[flow] done {name}", ok)
        except Exception as e:
            self._on_status(f"[flow] error {name}: {e}", False)
