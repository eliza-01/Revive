# app/launcher/sections/macros.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ..base import BaseSection
from core.engines.macros.runner import run_macros
from core.state.pool import pool_write, pool_get


class MacrosSection(BaseSection):
    """
    UI-API для макросов (ТОЛЬКО новый формат).
    rows: [{key, cast_s, repeat_s}]
    """

    def __init__(self, window, controller, state):
        super().__init__(window, state)
        self.controller = controller

    # ---- getters ----
    def macros_get(self) -> Dict[str, Any]:
        """Отдаём в UI актуальное состояние из пула для первичной загрузки."""
        try:
            enabled = bool(pool_get(self.s, "features.macros.enabled", False))
            repeat_enabled = bool(pool_get(self.s, "features.macros.repeat_enabled", False))
            rows = list(pool_get(self.s, "features.macros.rows", []) or [])
            # мягкая нормализация (защита от мусора в prefs)
            norm: List[Dict[str, Any]] = []
            for r in rows:
                k = str((r or {}).get("key", "1"))[:1]
                if k not in "0123456789": k = "1"
                try:
                    cast_s = max(0, int(float((r or {}).get("cast_s", 0))))
                except Exception:
                    cast_s = 0
                try:
                    repeat_s = max(0, int(float((r or {}).get("repeat_s", 0))))
                except Exception:
                    repeat_s = 0
                norm.append({"key": k, "cast_s": cast_s, "repeat_s": repeat_s})
            return {"ok": True, "enabled": enabled, "repeat_enabled": repeat_enabled, "rows": norm}
        except Exception as e:
            console.log(f"[macros] macros_get error: {e}")
            return {"ok": False, "error": str(e)}


    # ---- setters (только новый UI) ----
    def macros_set_enabled(self, enabled: bool):
        pool_write(self.s, "features.macros", {"enabled": bool(enabled)})
        self.emit("macros", "Макросы: вкл" if enabled else "Макросы: выкл", True if enabled else None)

    def macros_set_repeat_enabled(self, enabled: bool):
        pool_write(self.s, "features.macros", {"repeat_enabled": bool(enabled)})
        self.emit("macросы", "Повтор: вкл" if enabled else "Повтор: выкл", True if enabled else None)

    def macros_set_rows(self, rows):
        """rows: [{key, cast_s, repeat_s}]"""
        norm: List[Dict[str, Any]] = []
        try:
            for r in rows or []:
                k = str(r.get("key", "1"))[:1]
                if k not in "0123456789": k = "1"
                cast_s = max(0, int(float(r.get("cast_s", 0))))
                repeat_s = max(0, int(float(r.get("repeat_s", 0))))
                norm.append({"key": k, "cast_s": cast_s, "repeat_s": repeat_s})
        except Exception:
            norm = []
        pool_write(self.s, "features.macros", {"rows": list(norm)})

    # ---- выполнение ----
    def macros_run_once(self) -> bool:
        rows = list(pool_get(self.s, "features.macros.rows", []) or [])
        if not rows:
            self.emit("macros", "Список макросов пуст — нечего выполнять", False)
            return False

        ok = run_macros(
            server=pool_get(self.s, "config.server", "boh"),
            controller=self.controller,
            get_window=lambda: pool_get(self.s, "window.info", None),
            get_language=lambda: pool_get(self.s, "config.language", "rus"),
            cfg={"rows": rows},
            should_abort=lambda: False,
        )
        return bool(ok)

    # ---- экспорт в pywebview ----
    def expose(self) -> dict:
        return {
            "macros_get": self.macros_get,  # ← добавили
            "macros_set_enabled": self.macros_set_enabled,
            "macros_set_repeat_enabled": self.macros_set_repeat_enabled,
            "macros_set_rows": self.macros_set_rows,
            "macros_run_once": self.macros_run_once,
        }
