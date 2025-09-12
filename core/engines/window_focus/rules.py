# core/engines/window_focus/rules.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional

from core.state.pool import pool_get, pool_write
from core.logging import console


def make_focus_pause_rule(state: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None):
    """
    Пауза всех процессов, если окно без фокуса дольше grace_seconds.
    При возврате фокуса — восстановить сохранённые флаги и возобновить то, что было busy.
    Дополнительно: останавливаем/запускаем сервис чтения HP.

    Своё состояние хранит ТОЛЬКО в пуле:
      runtime.focus_pause.active: bool
      runtime.focus_pause.saved:      {respawn,buff,macros,tp,autofarm} -> bool
      runtime.focus_pause.saved_busy: {respawn,buff,macros,tp,autofarm} -> bool
    """
    return _FocusPauseRule(state, cfg or {})


class _FocusPauseRule:
    def __init__(self, state: Dict[str, Any], cfg: Dict[str, Any]):
        self.s = state
        self.grace = float(cfg.get("grace_seconds", 0.4))  # сек

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

    def _save_feature_busy(self) -> Dict[str, bool]:
        return {
            "respawn":  bool(pool_get(self.s, "features.respawn.busy",  False)),
            "buff":     bool(pool_get(self.s, "features.buff.busy",     False)),
            "macros":   bool(pool_get(self.s, "features.macros.busy",   False)),
            "tp":       bool(pool_get(self.s, "features.tp.busy",       False)),
            "autofarm": bool(pool_get(self.s, "features.autofarm.busy", False)),
        }

    def _restore_feature_flags(self, saved: Dict[str, bool]) -> None:
        # Не затираем изменения, сделанные во время паузы (OR сохранённого с текущим)
        for feat, was_enabled in (saved or {}).items():
            path = f"features.{feat}"
            cur = bool(pool_get(self.s, f"{path}.enabled", False))
            pool_write(self.s, path, {"enabled": bool(was_enabled) or cur})

    def _resume_were_busy(self, saved_busy: Dict[str, bool]) -> None:
        """
        По возврату фокуса возобновляем только то, что реально было «в работе».
        Ничего не бампим, ничего не включаем насильно — уважаем enabled.
        """
        services = self.s.get("_services") or {}

        # Автофарм: если был busy и всё ещё включён — запускаем один цикл
        try:
            if saved_busy.get("autofarm") and pool_get(self.s, "features.autofarm.enabled", False):
                af = services.get("autofarm")
                if hasattr(af, "run_once_now"):
                    af.run_once_now()
                    console.hud("succ", "Фокус вернулся — продолжаю автофарм")
        except Exception:
            pass

        # Макросы: сервис сам продолжит по is_focused; по ТЗ не бампим таймеры
        try:
            if saved_busy.get("macros") and pool_get(self.s, "features.macros.repeat_enabled", False):
                console.hud("succ", "Фокус вернулся — возобновляю повторы макросов")
        except Exception:
            pass

        # Buff/TP/Respawn — одношаговые; ими займётся пайплайн на ближайшем тике.

    # --- rule API ---
    def when(self, snap) -> bool:
        paused = self._is_paused()
        if (not paused) and (snap.is_focused is False) and (snap.focus_unfocused_for_s or 0) >= self.grace:
            return True
        if paused and (snap.is_focused is True):
            return True
        return False

    def run(self, snap) -> None:
        paused = self._is_paused()
        services = self.s.get("_services") or {}
        ps_service = services.get("player_state")

        if (not paused) and (snap.is_focused is False):
            # ВКЛЮЧИТЬ ПАУЗУ
            saved = self._save_feature_flags()

            prev_saved_busy = pool_get(self.s, "runtime.focus_pause.saved_busy", None)
            saved_busy = dict(prev_saved_busy) if prev_saved_busy else self._save_feature_busy()

            # стоп HP-сенсор
            try:
                if ps_service and ps_service.is_running():
                    ps_service.stop()
                    pool_write(self.s, "services.player_state", {"running": False})
            except Exception:
                pass

            self._set_paused(True, saved)
            pool_write(self.s, "runtime.focus_pause", {"saved_busy": dict(saved_busy)})

            console.hud("err", "Пауза: окно без фокуса — процессы остановлены")
            return

        if paused and (snap.is_focused is True):
            # СНЯТЬ ПАУЗУ
            saved = pool_get(self.s, "runtime.focus_pause.saved", {}) or {}
            saved_busy = pool_get(self.s, "runtime.focus_pause.saved_busy", {}) or {}

            self._restore_feature_flags(saved)
            self._set_paused(False, {})
            pool_write(self.s, "runtime.focus_pause", {"saved_busy": {}})

            # перезапуск HP-сервиса
            try:
                if ps_service and not ps_service.is_running():
                    ps_service.start()
                    pool_write(self.s, "services.player_state", {"running": True})
            except Exception:
                pass

            try:
                self._resume_were_busy(saved_busy)
            except Exception:
                pass

            console.hud("succ", "Фокус вернулся — возобновляем процессы")
