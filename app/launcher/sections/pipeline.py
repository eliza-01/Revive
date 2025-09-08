# app/launcher/sections/pipeline.py
from __future__ import annotations
from typing import Any, Dict, List
from ..base import BaseSection

_ALLOWED = ("respawn","macros","buff","tp","autofarm")

class PipelineSection(BaseSection):
    """
    Настройки порядка действий (пайплайн после смерти).
    Respawn всегда фиксирован первым.
    """
    def __init__(self, window, sys_state):
        super().__init__(window, sys_state)
        self.s.setdefault("pipeline_enabled", True)
        self.s.setdefault("pipeline_order", ["respawn","macros"])

    def _normalize(self, order: List[str]) -> List[str]:
        # respawn фиксирован первым, остальное — допустимые ключи без дублей
        tail = [x for x in order if x in _ALLOWED and x != "respawn"]
        seen = set()
        tail = [x for x in tail if (x not in seen and not seen.add(x))]
        # добавим отсутствующие допустимые шаги (в конец), чтобы не потерялись
        for k in _ALLOWED:
            if k != "respawn" and k not in tail:
                pass  # не обязаны добавлять автоматически
        return ["respawn"] + tail

    def pipeline_get_order(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.s.get("pipeline_enabled", True)),
            "order": list(self.s.get("pipeline_order") or ["respawn","macros"]),
            "allowed": list(_ALLOWED),
        }

    def pipeline_set_order(self, order: List[str]):
        try:
            norm = self._normalize([str(x).lower() for x in (order or [])])
        except Exception:
            norm = ["respawn","macros"]
        self.s["pipeline_order"] = norm
        self.emit("pipeline", f"Порядок действий: {', '.join(norm)}", None)

    def pipeline_set_enabled(self, enabled: bool):
        self.s["pipeline_enabled"] = bool(enabled)
        self.emit("pipeline", "Цепочка: вкл" if enabled else "Цепочка: выкл",
                  True if enabled else None)

    def expose(self) -> dict:
        return {
            "pipeline_get_order": self.pipeline_get_order,
            "pipeline_set_order": self.pipeline_set_order,
            "pipeline_set_enabled": self.pipeline_set_enabled,
        }
