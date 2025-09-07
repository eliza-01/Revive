# core/engines/macros/service.py
from __future__ import annotations
from typing import Callable, Optional, Dict, Any, List
import threading, time

from core.engines.macros.runner import run_macros


class MacrosRepeatService:
    """
    Фоновый сервис повтора макросов по полю repeat_s > 0.
    Интерфейс: start(), stop(), is_running()
    """

    def __init__(
        self,
        server: Callable[[], str],
        controller: Any,
        get_window: Callable[[], Optional[Dict]],
        get_language: Callable[[], str],
        get_rows: Callable[[], List[Dict[str, Any]]],
        is_enabled: Callable[[], bool],
        on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
    ):
        self._server = server
        self._controller = controller
        self._get_window = get_window
        self._get_language = get_language
        self._get_rows = get_rows
        self._is_enabled = is_enabled
        self._on_status = on_status or (lambda *_: None)

        self._thr: Optional[threading.Thread] = None
        self._run = False
        self._last_exec: Dict[int, float] = {}  # key: row id (index), value: last run time

    def is_running(self) -> bool:
        return bool(self._run)

    def start(self, poll_interval: float = 1.0):
        if self._run:
            return
        self._run = True
        self._thr = threading.Thread(target=self._loop, args=(poll_interval,), daemon=True)
        self._thr.start()

    def stop(self):
        self._run = False

    def _loop(self, poll_interval: float):
        while self._run:
            try:
                if not self._is_enabled():
                    time.sleep(poll_interval)
                    continue

                now = time.time()
                rows = list(self._get_rows() or [])
                to_run = []

                for idx, row in enumerate(rows):
                    repeat_s = max(0, float(row.get("repeat_s") or 0))
                    if repeat_s <= 0:
                        continue
                    last_ts = self._last_exec.get(idx, 0)
                    if now - last_ts >= repeat_s:
                        to_run.append((idx, row))

                for idx, row in to_run:
                    self._last_exec[idx] = time.time()
                    self._run_row(row)

            except Exception as e:
                print("[macros/service] error:", e)

            time.sleep(poll_interval)

    def _run_row(self, row: Dict[str, Any]):
        ok = run_macros(
            server=self._server(),
            controller=self._controller,
            get_window=self._get_window,
            get_language=self._get_language,
            on_status=self._on_status,
            cfg={"rows": [row]},
            should_abort=lambda: (not self._is_enabled()),
        )
        self._on_status(f"Повтор макроса {row.get('key')} завершён", ok)
