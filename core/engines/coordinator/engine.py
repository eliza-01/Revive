from __future__ import annotations
from typing import Dict, Tuple, Optional, Dict as TDict

from .rules import UnfocusedReason, UiGuardReason


class CoordinatorEngine:
    """
    Универсальная сборка настроек координатора.
    Никакой привязки к серверу — дефолты подходят для всех профилей.
    """

    def __init__(
        self,
        *,
        grace_seconds: float = 0.4,
        reason_priority: Tuple[str, ...] = ("ui_guard", "unfocused"),
        features: Tuple[str, ...] = (
            "respawn", "buff", "macros", "teleport", "record", "autofarm", "stabilize", "ui_guard"
        ),
        services: Tuple[str, ...] = ("player_state", "macros_repeat", "autofarm"),
        reason_scopes: Optional[TDict[str, TDict[str, bool]]] = None,
        period_ms: int = 250,
    ):
        self.grace_seconds = float(grace_seconds)
        self.reason_priority = tuple(reason_priority)
        self.features = tuple(features)
        self.services = tuple(services)
        self.reason_scopes = dict(reason_scopes or {})
        self.period_ms = int(period_ms)

    def build(self) -> Dict:
        providers = [
            UnfocusedReason(grace_seconds=self.grace_seconds),
            UiGuardReason(),
        ]
        return {
            "providers": providers,
            "reason_priority": self.reason_priority,
            "features": self.features,
            "services": self.services,
            "reason_scopes": self.reason_scopes,
            "period_ms": self.period_ms,
        }
