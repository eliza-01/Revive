# core/engines/autofarm/service.py
from __future__ import annotations
import time
import threading
from typing import Dict, Any, Optional

from _archive.core.runtime import RepeaterThread
from _archive.core.runtime.dashboard_guard import DASHBOARD_GUARD
from core.engines.autofarm.runner import run_autofarm


class AutoFarmService:
    def __init__(self, controller, get_server, get_language, get_window, is_alive,
                 schedule=None, on_status=lambda *_: None,
                 is_dashboard_busy=lambda: DASHBOARD_GUARD.is_busy(), log=None, **_):
        self.controller = controller
        self.get_server = get_server
        self.get_language = get_language
        self.get_window = get_window
        self.is_alive = is_alive
        self.schedule = schedule or (lambda fn, ms: None)
        self.on_status = on_status
        self.is_dashboard_busy = is_dashboard_busy
        self._log = log or (lambda *a, **k: None)

        self.enabled = False
        self.mode = "auto"
        self._armed = False
        self._cfg: Dict[str, Any] = {}
        self._poll = RepeaterThread(self._tick, 0.5)

        # управление жизненным циклом воркера
        self._worker: Optional[threading.Thread] = None
        self._cancel_evt = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    # публично полезно (для UI)
    def is_running(self) -> bool:
        return self._running

    # should_abort для движка
    def _should_abort(self) -> bool:
        return self._cancel_evt.is_set()

    def arm(self):
        """Вооружить автозапуск (после post-TP)."""
        if self.enabled and self.mode == "auto":
            self._armed = True
            self._idle_since = 0.0
            if not self._poll.is_running():
                self._poll.start()

    def _spawn_worker(self, cfg: Dict[str, Any]):
        """Запускаем движок в отдельном потоке, с возможностью отмены."""
        with self._lock:
            if self._worker and self._worker.is_alive():
                return  # уже запущено
            self._cancel_evt.clear()
            self._worker = threading.Thread(target=self._runner, args=(cfg,), daemon=True)
            self._worker.start()

    def _runner(self, cfg: Dict[str, Any]):
        server = (self.get_server() or "l2mad").lower()
        self._running = True
        try:
            ok = bool(run_autofarm(
                server=server,
                controller=self.controller,
                get_window=self.get_window,
                get_language=self.get_language,
                on_status=self.on_status,
                cfg=cfg or {},
                should_abort=self._should_abort,
            ))
            # run_autofarm сам публикует статусы; этот финальный — мягкий резюме
            if ok:
                self.on_status("Автофарм завершён", True)
            else:
                self.on_status("Автофарм остановлен/ошибка", None)
        except Exception as e:
            self.on_status(f"[af] start error: {e}", False)
        finally:
            self._running = False
            self._cancel_evt.clear()

    def start(self, cfg: Dict[str, Any]) -> bool:
        """Совместимость: теперь это триггер запуска воркера."""
        self._spawn_worker(cfg)
        return True

    def _stop_worker(self):
        with self._lock:
            self._cancel_evt.set()
            w = self._worker
        if w and w.is_alive():
            w.join(timeout=2.0)

    def set_enabled(self, v: bool, cfg: Optional[Dict[str, Any]] = None):
        self.enabled = bool(v)
        if cfg is not None:
            self._cfg = dict(cfg)

        if not self.enabled:
            self._armed = False
            self._idle_since = 0.0
            self._stop_worker()  # ← глушим движок немедленно
            return

        if self.mode == "manual":
            self._spawn_worker(self._cfg)
        else:
            # auto: ждём явного arm() после ТП/маршрута
            self._armed = False
            self._idle_since = 0.0

        if not self._poll.is_running():
            self._poll.start()

    def set_mode(self, mode: str):
        self.mode = (mode or "auto").lower()
        if self.mode == "auto":
            self._armed = False
            self._idle_since = 0.0

    _idle_since = 0.0
    def _tick(self):
        # не стартуем новый воркер, если уже идёт
        if not (self.enabled and self._armed):
            return
        if self._running:
            return
        if not self.is_alive():
            self._idle_since = 0.0
            return
        if self.is_dashboard_busy():
            self._idle_since = 0.0
            return
        now = time.time()
        if self._idle_since == 0.0:
            self._idle_since = now
            return
        if (now - self._idle_since) >= 1.5:
            self._armed = False
            self._spawn_worker(self._cfg)

    # --- шими для совместимости ---
    def register_pre_step(self, *_, **__):  return None
    def unregister_pre_step(self, *_, **__):  return None
    def register_post_step(self, *_, **__):  return None
    def unregister_post_step(self, *_, **__):  return None
