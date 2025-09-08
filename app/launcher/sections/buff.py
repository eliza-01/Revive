# app/launcher/sections/buffer.py
from __future__ import annotations
from typing import Any
from ..base import BaseSection

class BuffSection(BaseSection):
    """
    Управляет бафом:
      - включает/выключает флаг в UI-состоянии
      - выбирает режим/метод
      - выполняет разовый баф с верификацией «заряженности» и ограниченными повторами
    Верификация делается через ChargeChecker, который передаётся из SystemSection.
    """

    def __init__(self, window, controller, watcher, sys_state: dict, schedule, checker):
        super().__init__(window, sys_state)
        self.controller = controller
        self.watcher = watcher
        self.schedule = schedule
        self.checker = checker     # <- ChargeChecker, уже с зарегистрированными probes
        self._worker = None

        # параметры повторов (при необходимости потом вынесем в настройки)
        self._MAX_RETRIES = 2
        self._RETRY_DELAY_S = 1.0

    # --- внутреннее: создание worker-а бафа ---
    def _ensure_worker(self):
        from _archive.core.features.buff_after_respawn import BuffAfterRespawnWorker
        if not self._worker:
            self._worker = BuffAfterRespawnWorker(
                controller=self.controller,
                server=self.s["server"],
                get_window=lambda: self.s.get("window"),
                get_language=lambda: self.s["language"],
                on_status=lambda t, ok=None: self.emit("buffer", t, ok),
                click_threshold=0.87,
                debug=True,
            )
        # синхронизируем динамику
        self._worker.server = self.s["server"]
        try:
            # режим (profile/mage/fighter)
            if self.s.get("buff_mode"):
                self._worker.set_mode(self.s["buff_mode"])
            # метод бафа (через профиль сервера)
            if self.s.get("buff_method"):
                if hasattr(self.s.get("profile"), "set_buff_mode"):
                    self.s["profile"].set_buff_mode(self.s["buff_method"])
        except Exception:
            pass
        return self._worker

    # --- внутренняя проверка «заряженности» ---
    def _verify_charged(self) -> bool:
        try:
            val = self.checker.force_check()
            return bool(val is True)
        except Exception as e:
            self.emit("buffer", f"[charged] check failed: {e}", None)
            return False

    # --- API: переключатели/настройки ---
    def buff_set_enabled(self, enabled: bool):
        self.s["buff_enabled"] = bool(enabled)

    def buff_set_mode(self, mode: str):
        self.s["buff_mode"] = (mode or "profile").lower()

    def buff_set_method(self, method: str):
        self.s["buff_method"] = method or ""
        try:
            prof = self.s.get("profile")
            if hasattr(prof, "set_buff_mode"):
                prof.set_buff_mode(self.s["buff_method"])
        except Exception:
            pass

    # --- API: выполнение бафа с проверкой зарядки и повторами ---
    def buff_run_once(self) -> bool:
        if not self.s.get("window"):
            self.emit("buffer", "Окно не найдено", False)
            return False

        w = self._ensure_worker()

        attempt = 0
        while True:
            # 1) нажатие бафа
            ok = bool(w.run_once())
            if not ok:
                self.emit("buffer", "Баф не выполнен", False)
                return False

            # 2) проверка «заряженности»
            charged = self._verify_charged()
            if charged:
                self.emit("buffer", "Баф выполнен (заряд есть)", True)
                return True

            # 3) нет зарядки — делаем ограниченные повторы
            if attempt >= self._MAX_RETRIES:
                # Баф был нажат, но иконки зарядки не увидели — завершаем нейтральным статусом
                self.emit("buffer", "Баф выполнен, но заряд не обнаружен после повторов", None)
                return True

            attempt += 1
            self.emit("buffer", f"Заряд не обнаружен, повтор {attempt}/{self._MAX_RETRIES}…", None)
            try:
                import time
                time.sleep(self._RETRY_DELAY_S)
            except Exception:
                pass

    # --- экспорт в webview ---
    def expose(self) -> dict[str, Any]:
        return {
            "buff_set_enabled": self.buff_set_enabled,
            "buff_set_mode": self.buff_set_mode,
            "buff_set_method": self.buff_set_method,
            "buff_run_once": self.buff_run_once,
        }
