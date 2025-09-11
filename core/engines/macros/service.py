from __future__ import annotations
from typing import Callable, Optional, Dict, Any, List
import threading, time

from core.engines.macros.runner import run_macros


class MacrosRepeatService:
    """
    Фоновый сервис повтора макросов по полю repeat_s > 0.
    Внешние факторы:
      - включена ли функция повторов (is_enabled)
      - жив ли персонаж (is_alive: True/False/None)
      - есть ли фокус у окна игры (is_focused)

    Интерфейс: start(), stop(), is_running(), bump_all()
    """

    def __init__(
        self,
        server: Callable[[], str],
        controller: Any,
        get_window: Callable[[], Optional[Dict[str, Any]]],
        get_language: Callable[[], str],
        get_rows: Callable[[], List[Dict[str, Any]]],
        is_enabled: Callable[[], bool],
        on_status: Optional[Callable[[str, Optional[bool]], None]] = None,
        *,
        # None означает «неизвестно» (например, потерян фокус и виталы не читаем).
        is_alive: Optional[Callable[[], Optional[bool]]] = None,
        is_focused: Optional[Callable[[], bool]] = None,
        set_busy: Optional[Callable[[bool], None]] = None,   # ← коллбек для features.macros.busy
    ):
        self._server = server
        self._controller = controller
        self._get_window = get_window
        self._get_language = get_language
        self._get_rows = get_rows
        self._is_enabled = is_enabled
        self._on_status = on_status or (lambda *_: None)
        self._is_alive = is_alive or (lambda: True)
        self._is_focused = is_focused or (lambda: True)
        self._set_busy = set_busy or (lambda _b: None)

        self._thr: Optional[threading.Thread] = None
        self._run = False
        self._last_exec: Dict[int, float] = {}   # key: row index, value: last run time
        self._was_alive: Optional[bool] = None   # строгое отслеживание False→True для респавна
        self._was_focused: Optional[bool] = None

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
        try:
            self._set_busy(False)
        except Exception:
            pass

    def bump_all(self):
        """Сдвинуть «отсчёт до повтора» на 'сейчас'. Использовать ТОЛЬКО после респавна."""
        try:
            now = time.time()
            rows = list(self._get_rows() or [])
            for idx, row in enumerate(rows):
                repeat_s = max(0.0, float(row.get("repeat_s") or 0))
                if repeat_s > 0:
                    self._last_exec[idx] = now
        except Exception:
            pass

    def _loop(self, poll_interval: float):
        while self._run:
            try:
                if not self._is_enabled():
                    self._set_busy(False)
                    time.sleep(poll_interval)
                    continue

                # alive_raw: True/False/None  (None = неизвестно, НЕ трактуем как смерть)
                alive_raw = self._is_alive()
                alive = True if alive_raw is True else False if alive_raw is False else None
                focused = bool(self._is_focused())

                # первичная инициализация
                if self._was_alive is None:
                    self._was_alive = alive
                if self._was_focused is None:
                    self._was_focused = focused

                # детект респавна: строго False -> True
                respawn_happened = (self._was_alive is False and alive is True)
                if respawn_happened:
                    self.bump_all()
                    self._on_status("Сброс таймеров повторов после респавна", None)

                # обновляем прошлые значения
                self._was_alive = alive
                self._was_focused = focused

                # условия паузы:
                if (not focused) or (alive is False):
                    self._set_busy(False)
                    time.sleep(poll_interval)
                    continue
                # alive is None и есть фокус → работаем как обычно

                # планирование запусков
                now = time.time()
                rows = list(self._get_rows() or [])
                to_run = []

                for idx, row in enumerate(rows):
                    repeat_s = max(0.0, float(row.get("repeat_s") or 0))
                    if repeat_s <= 0:
                        continue
                    last_ts = self._last_exec.get(idx, 0.0)
                    if now - last_ts >= repeat_s:
                        to_run.append((idx, row))

                for idx, row in to_run:
                    self._last_exec[idx] = time.time()  # фиксируем старт ДО выполнения
                    self._run_row(row)

            except Exception as e:
                print("[macros/service] error:", e)

            time.sleep(poll_interval)

    def _run_row(self, row: Dict[str, Any]):
        self._set_busy(True)
        try:
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
        finally:
            self._set_busy(False)
