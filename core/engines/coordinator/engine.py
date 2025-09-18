# core/engines/coordinator/engine.py
from __future__ import annotations
from typing import Dict, Tuple, Optional, Dict as TDict

from .rules import Cor1Reason, Cor2Reason


class CoordinatorEngine:
    """
    Универсальная сборка координатора (только cor_1 и cor_2).
    """

    def __init__(
        self,
        *,
        grace_seconds: float = 0.4,  # сейчас не используется здесь; оставлен для совместимости
        reason_priority: Tuple[str, ...] = ("cor_2", "cor_1"),
        # ui_guard исключён из списка фич (его координируем отдельно)
        features: Tuple[str, ...] = (
            "respawn", "buff", "macros", "teleport", "record", "autofarm", "stabilize"
        ),
        services: Tuple[str, ...] = ("player_state", "macros_repeat", "autofarm"),
        reason_scopes: Optional[TDict[str, TDict[str, bool]]] = None,
        period_ms: int = 500,
    ):
        self.reason_priority = tuple(reason_priority)
        self.features = tuple(features)
        self.services = tuple(services)
        self.reason_scopes = dict(reason_scopes or {})
        self.period_ms = int(period_ms)

    def build(self) -> Dict:
        providers = [
            Cor2Reason(),  # alive=True & hp=None & autofarm.busy=True → cor_2
            Cor1Reason(),  # unfocused & !ui_guard.busy → cor_1
        ]
        return {
            "providers": providers,
            "reason_priority": self.reason_priority,
            "features": self.features,
            "services": self.services,
            "reason_scopes": self.reason_scopes,
            "period_ms": self.period_ms,
        }
