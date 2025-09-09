# app/launcher/sections/pipeline.py
from __future__ import annotations
from typing import Dict, List
from ..base import BaseSection
from core.state.pool import pool_write, pool_get

ALLOWED_STEPS_DEFAULT = ["respawn", "buff", "macros", "tp", "autofarm"]

class PipelineSection(BaseSection):
    def __init__(self, window, state: Dict[str, any]):
        super().__init__(window, state)
        # Инициализация по умолчанию (если ещё не заполнено)
        if pool_get(self.s, "pipeline.allowed", None) is None:
            pool_write(self.s, "pipeline", {
                "allowed": list(ALLOWED_STEPS_DEFAULT),
                "order": ["respawn", "macros"],
            })

    def _sanitize(self, order: List[str]) -> List[str]:
        allowed = [x for x in (pool_get(self.s, "pipeline.allowed", ALLOWED_STEPS_DEFAULT) or []) if isinstance(x, str)]
        uniq: List[str] = []
        for k in order or []:
            k = (k or "").strip().lower()
            if k in allowed and k not in uniq:
                uniq.append(k)

        # «respawn» должен быть первым
        if "respawn" not in uniq:
            uniq.insert(0, "respawn")
        else:
            uniq = ["respawn"] + [k for k in uniq if k != "respawn"]
        return uniq

    def pipeline_get_order(self) -> Dict[str, any]:
        return {
            "order": list(pool_get(self.s, "pipeline.order", ["respawn", "macros"]) or ["respawn"]),
            "allowed": list(pool_get(self.s, "pipeline.allowed", ALLOWED_STEPS_DEFAULT) or ALLOWED_STEPS_DEFAULT),
        }

    def pipeline_set_order(self, order):
        """
        order: список шагов из UI (например: ["respawn","buff","tp","macros"])
        Храним как есть; PipelineRule всё равно зафиксирует respawn вверху.
        """
        try:
            seq = [str(x).lower().strip() for x in (order or []) if x]
        except Exception:
            seq = []

        allowed = {"respawn", "buff", "tp", "macros", "autofarm"}
        seen = set()
        seq = [x for x in seq if x in allowed and (x not in seen and not seen.add(x))]

        pool_write(self.s, "pipeline", {"order": list(seq)})
        self.emit("pipeline", f"Порядок сохранён: {', '.join(seq)}", None)
        return True

    def expose(self) -> dict:
        return {
            "pipeline_get_order": self.pipeline_get_order,
            "pipeline_set_order": self.pipeline_set_order,
        }
