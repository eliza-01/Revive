# core/engines/coordinator/runner.py
from __future__ import annotations
from typing import Dict, Any

from core.logging import console
from .service import CoordinatorService


class CoordinatorRunner:
    """
    Тонкая фасадка над CoordinatorService:
    - простой API для UI/секций/правил,
    - место для будущих метрик/логов.
    """
    def __init__(self, state: Dict[str, Any], service: CoordinatorService):
        self.state = state
        self.service = service

    def set_reason(self, reason: str, active: bool) -> Dict[str, Any]:
        try:
            self.service.set_reason_active(str(reason or ""), bool(active))
            return {"ok": True}
        except Exception as e:
            console.log(f"[coordinator.runner] set_reason error: {e}")
            return {"ok": False, "error": str(e)}

    def state_info(self) -> Dict[str, Any]:
        return {"running": self.service.is_running()}

    def reasons(self) -> Dict[str, Any]:
        try:
            return self.service.reasons_snapshot()
        except Exception:
            return {"reasons": {}, "pipeline": {"paused": False, "reason": ""}}
