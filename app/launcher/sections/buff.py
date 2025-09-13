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

    # --- setters ---
    def buff_set_enabled(self, enabled: bool):
        pool_write(self.s, "features.buff", {"enabled": bool(enabled)})
        self.emit("buff", "Баф: вкл" if enabled else "Баф: выкл", True if enabled else None)

    def buff_set_mode(self, mode: str):
        modes = set(pool_get(self.s, "features.buff.modes", []) or [])
        m = (mode or "").strip().lower()
        if modes and m not in modes:
            self.emit("buff", f"Неизвестный режим бафа: {mode}", None)
        pool_write(self.s, "features.buff", {"mode": mode or ""})

    def buff_set_method(self, method: str):
        methods = set(pool_get(self.s, "features.buff.methods", []) or [])
        m = (method or "").strip().lower()
        if methods and m not in methods:
            self.emit("buff", f"Неизвестный метод бафа: {method}", None)
        pool_write(self.s, "features.buff", {"method": m})

    # --- checker ---
    def buff_checker_get(self) -> list[str]:
        return list(pool_get(self.s, "features.buff.checker", []) or [])

    def buff_checker_set(self, items: list[str]) -> bool:
        try:
            items = [str(x).strip() for x in (items or []) if x]
            pool_write(self.s, "features.buff", {"checker": items})
            self.emit("buff", f"Checker обновлён ({len(items)} шт.)", True)
            return True
        except Exception:
            self.emit("buff", "Ошибка обновления Checker", False)
            return False

    # --- getters ---
    def buff_get_config(self) -> Dict[str, Any]:
        return {
            "enabled": bool(pool_get(self.s, "features.buff.enabled", False)),
            "mode": pool_get(self.s, "features.buff.mode", ""),
            "method": pool_get(self.s, "features.buff.method", ""),
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
        return True

    def expose(self) -> dict:
        return {
            "buff_set_enabled": self.buff_set_enabled,
            "buff_set_mode": self.buff_set_mode,
            "buff_set_method": self.buff_set_method,
            "buff_get_config": self.buff_get_config,
            "buff_run_once": self.buff_run_once,
            "buff_checker_get": self.buff_checker_get,   # ← добавлено
            "buff_checker_set": self.buff_checker_set,   # ← добавлено
        }
