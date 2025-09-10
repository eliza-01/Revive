# core/engines/window_focus/rules.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional
import time

from core.state.pool import pool_get, pool_write


def make_focus_pause_rule(state: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None):
    """
    Пауза всех процессов, если окно без фокуса дольше grace_seconds.
    При возврате фокуса — восстановить сохранённые флаги.
    Дополнительно: останавливаем/запускаем сервис чтения HP.

    Хранит своё состояние ТОЛЬКО в пуле:
      runtime.focus_pause.active: bool
      runtime.focus_pause.saved:  {respawn,buff,macros,tp,autofarm} → bool
    """
    return _FocusPauseRule(state, cfg or {})


class _FocusPauseRule:
    def __init__(self, state: Dict[str, Any], cfg: Dict[str, Any]):
        self.s = state
        self.grace = float(cfg.get("grace_seconds", 1.0))  # сек

    # --- helpers ---
    def _is_paused(self) -> bool:
        return bool(pool_get(self.s, "runtime.focus_pause.active", False))

    def _set_paused(self, active: bool, saved: Optional[Dict[str, bool]] = None) -> None:
        if saved is None:
            saved = pool_get(self.s, "runtime.focus_pause.saved", {}) or {}
        pool_write(self.s, "runtime.focus_pause", {"active": bool(active), "saved": dict(saved)})

    def _save_feature_flags(self) -> Dict[str, bool]:
        return {
            "respawn":  bool(pool_get(self.s, "features.respawn.enabled", False)),
            "buff":     bool(pool_get(self.s, "features.buff.enabled", False)),
            "macros":   bool(pool_get(self.s, "features.macros.enabled", False)),
            "tp":       bool(pool_get(self.s, "features.tp.enabled", False)),
            "autofarm": bool(pool_get(self.s, "features.autofarm.enabled", False)),
        }

    def _restore_feature_flags(self, saved: Dict[str, bool]) -> None:
        # Не затираем изменения, сделанные во время паузы (OR сохранённого с текущим)
        for feat, was_enabled in (saved or {}).items():
            path = f"features.{feat}"
            cur = bool(pool_get(self.s, f"{path}.enabled", False))
            pool_write(self.s, path, {"enabled": bool(was_enabled) or cur})

    # --- rule API ---
    def when(self, snap) -> bool:
        paused = self._is_paused()
        # активировать паузу: не на паузе и без фокуса ≥ grace
        if (not paused) and (snap.has_focus is False) and (snap.focus_unfocused_for_s or 0) >= self.grace:
            return True
        # снять паузу: пауза активна и фокус вернулся
        if paused and (snap.has_focus is True):
            return True
        return False

    def run(self, snap) -> None:
        paused = self._is_paused()
        ui_emit: Optional[Callable[[str, str, Optional[bool]], None]] = self.s.get("ui_emit")
        services = self.s.get("_services") or {}
        ps_service = services.get("player_state")

        if (not paused) and (snap.has_focus is False):
            # ВКЛЮЧИТЬ ПАУЗУ
            saved = self._save_feature_flags()

            # стоп HP-сенсор
            try:
                if ps_service and ps_service.is_running():
                    ps_service.stop()
                    pool_write(self.s, "services.player_state", {"running": False})
            except Exception:
                pass

            # Сброс vitals делает WindowFocusService при потере фокуса;
            # тут только фиксируем состояние правила.
            self._set_paused(True, saved)

            try:
                if callable(ui_emit):
                    ui_emit("postrow", "Пауза: окно без фокуса — процессы остановлены", None)
            except Exception:
                pass
            return

        if paused and (snap.has_focus is True):
            # СНЯТЬ ПАУЗУ
            saved = pool_get(self.s, "runtime.focus_pause.saved", {}) or {}

            # восстановить флаги фич
            self._restore_feature_flags(saved)
            self._set_paused(False, {})

            # перезапуск HP-сервиса
            try:
                if ps_service and not ps_service.is_running():
                    ps_service.start()
                    pool_write(self.s, "services.player_state", {"running": True})
            except Exception:
                pass

            try:
                if callable(ui_emit):
                    ui_emit("postrow", "Фокус вернулся — возобновляем процессы", True)
            except Exception:
                pass
