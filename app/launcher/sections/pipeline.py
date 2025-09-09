from __future__ import annotations
from typing import Any, Dict, List
from ..base import BaseSection

from core.state.pool import pool_merge

ALLOWED_STEPS_DEFAULT = ["respawn", "buff", "macros", "tp", "autofarm"]

class PipelineSection(BaseSection):
    def __init__(self, window, sys_state: Dict[str, Any]):
        super().__init__(window, sys_state)
        self.s.setdefault("pipeline_allowed", list(ALLOWED_STEPS_DEFAULT))
        # по умолчанию: респавн → макросы (остальные можно подтянуть позже)
        self.s.setdefault("pipeline_order", ["respawn", "macros"])

        pool_merge(self.s, "pipeline", {
            "allowed": list(self.s.get("pipeline_allowed") or []),
            "order": list(self.s.get("pipeline_order") or []),
        })

    def _sanitize(self, order: List[str]) -> List[str]:
        allowed = [x for x in (self.s.get("pipeline_allowed") or []) if isinstance(x, str)]
        # уникализируем, фильтруем неразрешённые
        uniq = []
        for k in order or []:
            k = (k or "").strip().lower()
            if k in allowed and k not in uniq:
                uniq.append(k)

        # «respawn» должен быть первым
        if "respawn" not in uniq:
            uniq.insert(0, "respawn")
        else:
            uniq = ["respawn"] + [k for k in uniq if k != "respawn"]

        # если кто-то добавил новый разрешённый шаг, которого нет в списке — он попадёт в конец при желании
        return uniq

    def pipeline_get_order(self) -> Dict[str, Any]:
        return {
            "order": list(self.s.get("pipeline_order") or ["respawn"]),
            "allowed": list(self.s.get("pipeline_allowed") or ALLOWED_STEPS_DEFAULT),
        }

    def pipeline_set_order(self, order):
        """
        order: список шагов из UI (например: ["respawn","buff","tp","macros"])
        Храним как есть; сам PipelineRule всё равно зафиксирует respawn вверху.
        """
        try:
            seq = [str(x).lower().strip() for x in (order or []) if x]
        except Exception:
            seq = []

        # опционально — отфильтровать неожиданные значения и дубликаты
        allowed = {"respawn", "buff", "tp", "macros", "autofarm"}
        seen = set()
        seq = [x for x in seq if x in allowed and (x not in seen and not seen.add(x))]

        self.s["pipeline_order"] = seq
        pool_merge(self.s, "pipeline", {"order": list(seq)})
        self.emit("pipeline", f"Порядок сохранён: {', '.join(seq)}", None)
        return True

    def expose(self) -> dict:
        return {
            "pipeline_get_order": self.pipeline_get_order,
            "pipeline_set_order": self.pipeline_set_order,
        }
