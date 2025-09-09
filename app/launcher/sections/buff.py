# app/launcher/sections/buff.py
from __future__ import annotations
from typing import Any, Dict, Optional
from ..base import BaseSection
from core.state.pool import pool_write, pool_get

TP_METHOD_DASHBOARD = "dashboard"
TP_METHOD_GATEKEEPER = "gatekeeper"

class BuffSection(BaseSection):
    """
    Управление бафом целиком через пул.
    Здесь только конфиг/кнопки UI. Исполнение шага 'buff' в пайплайне делает правило/движок.
    """

    def __init__(self, window, controller, ps_adapter, state: Dict[str, Any], schedule, checker: Optional[Any] = None):
        super().__init__(window, state)
        self.controller = controller
        self.ps = ps_adapter
        self.schedule = schedule
        self.checker = checker

        # ensure defaults exist (ensure_pool уже сделал, но обновим методы от профиля при первом создании)
        # методы/текущий метод уже проставляются в SystemSection, так что здесь ничего не нужно.

    # --- setters ---
    def buff_set_enabled(self, enabled: bool):
        pool_write(self.s, "features.buff", {"enabled": bool(enabled)})
        self.emit("buff", "Баф: вкл" if enabled else "Баф: выкл", True if enabled else None)

    def buff_set_mode(self, mode: str):
        methods = set(pool_get(self.s, "features.buff.methods", []) or [])
        m = (mode or "").strip().lower()
        if methods and m not in methods:
            # неизвестный метод — пометим предупреждением, но сохраним как есть (вдруг профиль обновится)
            self.emit("buff", f"Неизвестный метод бафа: {mode}", None)
        pool_write(self.s, "features.buff", {"mode": mode or ""})

    # --- getters ---
    def buff_get_config(self) -> Dict[str, Any]:
        return {
            "enabled": bool(pool_get(self.s, "features.buff.enabled", False)),
            "mode": pool_get(self.s, "features.buff.mode", ""),
            "methods": list(pool_get(self.s, "features.buff.methods", []) or []),
        }

    # --- manual run hook (опционально из UI) ---
    def buff_run_once(self) -> bool:
        """
        Запуск разового бафа из UI. Само применение зависит от движка.
        Здесь только статус; фактическая реализация шага — в оркестраторе/правиле.
        """
        en = bool(pool_get(self.s, "features.buff.enabled", False))
        if not en:
            self.emit("buff", "Баф отключён", None)
            return False
        mode = pool_get(self.s, "features.buff.mode", "")
        self.emit("buff", f"Запуск бафа (режим: {mode or '—'})", None)
        # если есть отдельный движок/сервис — вызвать здесь.
        # пока просто возвращаем True как “акция принята”.
        return True

    def expose(self) -> dict:
        return {
            "buff_set_enabled": self.buff_set_enabled,
            "buff_set_mode": self.buff_set_mode,
            "buff_get_config": self.buff_get_config,
            "buff_run_once": self.buff_run_once,
        }
