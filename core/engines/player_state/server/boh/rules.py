from __future__ import annotations
from typing import Any, Dict

from core.state.pool import pool_get


class HPZeroTriggersUiGuard:
    """
    Если hp_ratio ≈ 0 — запустить один проход UI-Guard и замаскировать виталы до следующего тика PS.
    Паузы/маску при overlay обрабатывает тонкая интеграция в сервисах UI.
    """

    def __init__(self, api):
        self.api = api  # ensure_ui_guard_runner(), mask_vitals(), hud()

    def evaluate(self, state: Dict[str, Any], now: float) -> None:
        # Сервис PS на паузе — ничего не делаем
        if pool_get(state, "services.player_state.paused", False):
            return

        # UI-Guard уже в работе — не дублируем
        if pool_get(state, "features.ui_guard.busy", False):
            return

        hp = pool_get(state, "player.hp_ratio", None)
        try:
            hp = None if hp is None else float(hp)
        except Exception:
            hp = None

        if hp is None:
            return

        if hp <= 0.001:
            runner = self.api.ensure_ui_guard_runner()
            if runner is None:
                return
            try:
                runner.run_once()
            except Exception:
                pass
            # После запуска очистки — виталы считаем неизвестными до нового тика PS
            self.api.mask_vitals()
            # по вкусу: уведомление
            # self.api.hud("att", "HP≈0 — запускаю UI-Guard")


def build_rules(api):
    # Для BOH достаточно одного правила (hp≈0 → ui_guard). Остальное — в слое UI.
    return [HPZeroTriggersUiGuard(api)]
