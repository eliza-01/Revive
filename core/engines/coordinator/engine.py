# core/engines/coordinator/engine.py
from __future__ import annotations
from typing import Dict, Tuple, Optional, Dict as TDict

from .rules import UnfocusedReason, UiGuardReason, Cor1Reason, Cor2Reason, Cor3Reason


class CoordinatorEngine:
    """
    Универсальная сборка настроек координатора.
    Никакой привязки к серверу — дефолты подходят для всех профилей.
    """

    def __init__(
        self,
        *,
        grace_seconds: float = 0.4,
        # Приоритет нужен для выбора "видимой" причины (pipeline/и т.п.)
        reason_priority: Tuple[str, ...] = ("cor_3", "ui_guard", "cor_2", "cor_1", "unfocused"),
        # ВАЖНО: ui_guard исключён из списка фич (его нельзя ставить на паузу "обычно")
        features: Tuple[str, ...] = (
            "respawn", "buff", "macros", "teleport", "record", "autofarm", "stabilize"
        ),
        services: Tuple[str, ...] = ("player_state", "macros_repeat", "autofarm"),
        reason_scopes: Optional[TDict[str, TDict[str, bool]]] = None,
        # Тики координатора — 500 мс
        period_ms: int = 500,
    ):
        self.grace_seconds = float(grace_seconds)
        self.reason_priority = tuple(reason_priority)
        self.features = tuple(features)
        self.services = tuple(services)
        self.reason_scopes = dict(reason_scopes or {})
        self.period_ms = int(period_ms)

    def build(self) -> Dict:
        providers = [
            Cor3Reason(),                                 # ui_guard.busy & no focus → пауза самого ui_guard
            Cor2Reason(),                                 # alive=True & hp=None & autofarm.busy=True → cor_2
            Cor1Reason(),                                 # no focus & !ui_guard.busy → cor_1
            UnfocusedReason(grace_seconds=self.grace_seconds),
            UiGuardReason(),                              # пока гвард работает — все (кроме него) на паузе
        ]
        return {
            "providers": providers,
            "reason_priority": self.reason_priority,
            "features": self.features,
            "services": self.services,
            "reason_scopes": self.reason_scopes,
            "period_ms": self.period_ms,
        }
