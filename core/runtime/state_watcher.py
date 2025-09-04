# core/runtime/state_watcher.py
from __future__ import annotations
from typing import Callable, Optional, Dict
from core.features.archive.player_state import PlayerState, PlayerStateMonitor

class StateWatcher:
    """
    Только мониторинг: hp → alive/dead. Никаких кликов, бафов и т.п.
    Колбэки на каждое обновление, на переход в dead и на переход в alive.
    """
    def __init__(
            self,
            server: str,
            get_window: Callable[[], Optional[Dict]],
            get_language: Callable[[], str],
            poll_interval: float = 0.2,
            zero_hp_threshold: float = 0.01,
            on_state: Optional[Callable[[PlayerState], None]] = None,
            on_dead: Optional[Callable[[PlayerState], None]] = None,
            on_alive: Optional[Callable[[PlayerState], None]] = None,
            debug: bool = False,
    ):
        self.server = server
        self._get_window = get_window
        self._get_language = get_language
        self._thr = PlayerStateMonitor(
            server=server,
            get_window=get_window,
            on_update=self._on_update,
            poll_interval=poll_interval,
            debug=False,
        )
        self._zero = float(zero_hp_threshold)
        self._on_state = on_state
        self._on_dead = on_dead
        self._on_alive = on_alive
        self._debug = debug

        self._last: PlayerState = PlayerState()
        self._alive_flag: Optional[bool] = None  # неизвестно
        self._running = False          # ← инициализируем флаг

    # lifecycle
    def start(self):
        self._thr.start()
        self._running = True           # ← фикс

    def stop(self):
        self._thr.stop()
        self._running = False          # ← фикс

    def is_running(self) -> bool:
        try:
            return bool(self._thr.is_running())  # если у монитора есть метод
        except Exception:
            # иначе читаем наш флаг; при первом вызове до start() вернёт False
            return bool(self._running or getattr(self._thr, "_running", False))

    def set_server(self, server: str):
        self.server = server
        self._thr.set_server(server)

    # accessors
    def last(self) -> PlayerState: return self._last
    def is_alive(self) -> bool: return bool(getattr(self._last, "hp_ratio", 1.0) > self._zero)


    # internals
    def _on_update(self, st: PlayerState):
        self._last = st
        alive_now = bool(st.hp_ratio > self._zero)
        if callable(self._on_state):
            try: self._on_state(st)
            except: pass

        if self._alive_flag is None:
            # первый замер: зафиксировать и, если уже dead, сразу дернуть on_dead
            self._alive_flag = alive_now
            if not alive_now and callable(self._on_dead):
                try: self._on_dead(st)
                except: pass
            return

        if alive_now != self._alive_flag:
            self._alive_flag = alive_now
            cb = self._on_alive if alive_now else self._on_dead
            if callable(cb):
                try: cb(st)
                except: pass

