from __future__ import annotations
import time
from typing import Any, Callable, Dict, Optional

from core.engines.macros.runner import run_macros

class _MacrosRule:
    def __init__(self, sys_state: Dict[str, Any], controller, report: Callable[[str], None]):
        self.s = sys_state
        self.controller = controller
        self.report = report
        self._busy_until = 0.0
        self._running = False

    def _rows_from_state(self):
        # Новый формат (UI “Кнопка / Кастуется / Повторять через”)
        rows = list(self.s.get("macros_rows") or [])
        if rows:
            return rows
        # Фолбэк на старый формат (sequence + duration)
        seq = list(self.s.get("macros_sequence") or [])
        dur = int(float(self.s.get("macros_duration_s", 0)))
        return [{"key": str(k)[:1], "cast_s": max(0, dur), "repeat_s": 0} for k in seq] or [{"key": "1", "cast_s": 0, "repeat_s": 0}]

    def when(self, snap) -> bool:
        now = time.time()
        if now < self._busy_until or self._running:
            return False
        if not self.s.get("macros_enabled"):
            return False
        # базовый режим: запускаемся по флагу (manual). Триггеры “после бафа/ТП” добавим отдельно.
        return True

    def run(self, snap) -> None:
        self._running = True
        try:
            def _status(text: str, ok: Optional[bool] = None):
                # в HUD/UI уходит точно так же, как у респавна
                self.report(f"[MACROS] {text}")
                emit = self.s.get("ui_emit")
                if callable(emit):
                    emit("macros", text, ok)

            ok = run_macros(
                server=self.s.get("server") or "boh",
                controller=self.controller,
                get_window=lambda: self.s.get("window"),
                get_language=lambda: self.s.get("language") or "rus",
                on_status=_status,
                cfg={"rows": self._rows_from_state()},
                should_abort=lambda: (not self.s.get("macros_enabled", False)),
            )
            # запускаем ОДИН раз, повторы делает фоновый сервис
            self.s["macros_enabled"] = False
            self._busy_until = time.time() + (2.0 if ok else 4.0)
        finally:
            self._running = False

def make_macros_rule(sys_state, controller, report: Optional[Callable[[str], None]] = None):
    return _MacrosRule(sys_state, controller, report or (lambda _m: None))
