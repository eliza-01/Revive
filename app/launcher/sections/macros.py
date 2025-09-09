# app/launcher/sections/macros.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..base import BaseSection
from core.engines.macros.runner import run_macros
from core.state.pool import pool_write, pool_get

class MacrosSection(BaseSection):
    """
    UI-API для макросов.
    Поддерживает новый формат rows [{key, cast_s, repeat_s}] и хранит всё в пуле.
    """

    def __init__(self, window, controller, state):
        super().__init__(window, state)
        self.controller = controller

    # ---- setters (новый UI) ----
    def macros_set_enabled(self, enabled: bool):
        pool_write(self.s, "features.macros", {
            "enabled": bool(enabled),
            "repeat_enabled": bool(enabled),
        })
        self.emit("macros", "Макросы: вкл" if enabled else "Макросы: выкл", True if enabled else None)

    def macros_set_rows(self, rows):
        """
        rows: [{key, cast_s, repeat_s}, ...]
        key — цифра '0'..'9'
        cast_s — секунды (int >= 0)
        repeat_s — секунды (int >= 0)
        """
        norm: List[Dict[str, Any]] = []
        try:
            for r in rows or []:
                k = str(r.get("key", "1"))[:1]
                if k not in "0123456789":
                    k = "1"
                cast_s = max(0, int(float(r.get("cast_s", 0))))
                repeat_s = max(0, int(float(r.get("repeat_s", 0))))
                norm.append({"key": k, "cast_s": cast_s, "repeat_s": repeat_s})
        except Exception:
            norm = [{"key": "1", "cast_s": 0, "repeat_s": 0}]
        pool_write(self.s, "features.macros", {"rows": list(norm)})

    # ---- совместимость (старый UI вызывает эти методы) ----
    def macros_set_run_always(self, enabled: bool):
        pool_write(self.s, "features.macros", {"run_always": bool(enabled)})

    def macros_set_delay(self, seconds: float):
        pool_write(self.s, "features.macros", {"delay_s": max(0.0, float(seconds or 0))})

    def macros_set_duration(self, seconds: float):
        pool_write(self.s, "features.macros", {"duration_s": max(0.0, float(seconds or 0))})

    def macros_set_sequence(self, seq):
        seq_norm = [c[:1] for c in (seq or []) if (c and c[0] in "0123456789")] or ["1"]
        pool_write(self.s, "features.macros", {"sequence": seq_norm})

    # ---- выполнение ----
    def _rows_effective(self) -> List[Dict[str, Any]]:
        rows = list(pool_get(self.s, "features.macros.rows", []) or [])
        if rows:
            return rows

        # фолбэк на простые настройки — тоже из пула
        seq = list(pool_get(self.s, "features.macros.sequence", []) or [])
        dur = int(float(pool_get(self.s, "features.macros.duration_s", 0)))
        if not seq:
            seq = ["1"]
        return [{"key": str(k)[:1], "cast_s": max(0, dur), "repeat_s": 0} for k in seq]

    def macros_run_once(self) -> bool:
        rows = self._rows_effective()

        def _status(text: str, ok: Optional[bool] = None):
            self.emit("macros", text, ok)

        ok = run_macros(
            server=pool_get(self.s, "app.server", "boh"),
            controller=self.controller,
            get_window=lambda: pool_get(self.s, "window.info", None),
            get_language=lambda: pool_get(self.s, "app.language", "rus"),
            on_status=_status,
            cfg={"rows": rows},
            should_abort=lambda: False,
        )
        return bool(ok)

    # ---- экспорт в pywebview ----
    def expose(self) -> dict:
        return {
            # новый интерфейс
            "macros_set_enabled": self.macros_set_enabled,
            "macros_set_repeat_enabled": lambda enabled: pool_write(self.s, "features.macros", {"repeat_enabled": bool(enabled)}),
            "macros_set_rows": self.macros_set_rows,
            "macros_run_once": self.macros_run_once,

            # старый интерфейс (чтобы старый js не падал)
            "macros_set_run_always": self.macros_set_run_always,
            "macros_set_delay": self.macros_set_delay,
            "macros_set_duration": self.macros_set_duration,
            "macros_set_sequence": self.macros_set_sequence,
        }
