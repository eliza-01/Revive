# core/orchestrators/rules_base.py
from __future__ import annotations

class Rule:
    """Минимальный интерфейс правила оркестратора."""
    def when(self, snap) -> bool:  # должно быть очень дешёвым
        return False

    def run(self, snap) -> None:   # может быть «тяжёлым» (выполнить действие)
        pass
