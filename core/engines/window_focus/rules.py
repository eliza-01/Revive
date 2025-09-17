# core/engines/window_focus/rules.py
from __future__ import annotations
from typing import Any, Dict, Optional
import time

from core.state.pool import pool_get, pool_write
from core.logging import console


def make_focus_pause_rule(state: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None):
    """
    Политика паузы по фокусу:

    - если окно без фокуса дольше grace_seconds -> ставим паузу ('unfocused')
    - по возврату фокуса снимаем ТОЛЬКО 'unfocused'-паузы
    - сохраняем enabled-флаги и busy-срез (для бережного восстановления)
    - НИЧЕГО не стартуем/останавливаем: сервисы работают всегда и уважают флаги paused

    Своё состояние хранит ТОЛЬКО в:
      runtime.focus_pause.active: bool
      runtime.focus_pause.saved:      {respawn,buff,macros,teleport,autofarm} -> bool
      runtime.focus_pause.saved_busy: {respawn,buff,macros,teleport,autofarm} -> bool
    """
    return _FocusPauseRule(state, cfg or {})


class _FocusPauseRule:
    FEAT_KEYS = ("respawn","buff","macros","teleport","record","autofarm","stabilize","ui_guard")
    SERV_KEYS = ("player_state","macros_repeat","autofarm")

    def __init__(self, state: Dict[str, Any], cfg: Dict[str, Any]):
        self.s = state
        self.grace = float(cfg.get("grace_seconds", 0.4))

    # --- helpers ---
    def _is_paused(self) -> bool:
        return bool(pool_get(self.s, "runtime.focus_pause.active", False))

    def _set_paused_flag(self, active: bool, saved: Optional[Dict[str, bool]] = None) -> None:
        if saved is None:
            saved = pool_get(self.s, "runtime.focus_pause.saved", {}) or {}
        pool_write(self.s, "runtime.focus_pause", {"active": bool(active), "saved": dict(saved)})

    def _save_feature_enabled(self) -> Dict[str, bool]:
        return {
            "respawn":  bool(pool_get(self.s, "features.respawn.enabled", False)),
            "buff":     bool(pool_get(self.s, "features.buff.enabled", False)),
            "macros":   bool(pool_get(self.s, "features.macros.enabled", False)),
            "teleport": bool(pool_get(self.s, "features.teleport.enabled", False)),
            "autofarm": bool(pool_get(self.s, "features.autofarm.enabled", False)),
        }

    def _save_feature_busy(self) -> Dict[str, bool]:
        return {
            "respawn":  bool(pool_get(self.s, "features.respawn.busy",  False)),
            "buff":     bool(pool_get(self.s, "features.buff.busy",     False)),
            "macros":   bool(pool_get(self.s, "features.macros.busy",   False)),
            "teleport": bool(pool_get(self.s, "features.teleport.busy", False)),
            "autofarm": bool(pool_get(self.s, "features.autofarm.busy", False)),
        }

    def _apply_pause_flags(self, paused: bool, reason: str):
        now = time.time()
        if paused:
            # ставим 'unfocused'-паузы
            for fk in self.FEAT_KEYS:
                pool_write(self.s, f"features.{fk}", {"paused": True, "pause_reason": reason})
            for sk in self.SERV_KEYS:
                pool_write(self.s, f"services.{sk}", {"paused": True, "pause_reason": reason})
            pool_write(self.s, "pipeline", {"paused": True, "pause_reason": reason, "ts": now})
        else:
            # снимаем ТОЛЬКО 'unfocused'-паузы
            for fk in self.FEAT_KEYS:
                if pool_get(self.s, f"features.{fk}.pause_reason", "") == reason:
                    pool_write(self.s, f"features.{fk}", {"paused": False, "pause_reason": ""})
            for sk in self.SERV_KEYS:
                if pool_get(self.s, f"services.{sk}.pause_reason", "") == reason:
                    pool_write(self.s, f"services.{sk}", {"paused": False, "pause_reason": ""})
            pool_write(self.s, "pipeline", {"paused": False, "pause_reason": "", "ts": now})

    def _restore_feature_enabled(self, saved: Dict[str, bool]) -> None:
        # Не затираем изменения, сделанные во время паузы: OR сохранённого с текущим
        for feat, was_enabled in (saved or {}).items():
            path = f"features.{feat}"
            cur = bool(pool_get(self.s, f"{path}.enabled", False))
            pool_write(self.s, path, {"enabled": bool(was_enabled) or cur})

    def _resume_were_busy(self, saved_busy: Dict[str, bool]) -> None:
        services = self.s.get("_services") or {}

        # Автофарм — мягкий пинок одного цикла, если был занят и включён
        try:
            if saved_busy.get("autofarm") and pool_get(self.s, "features.autofarm.enabled", False):
                af = services.get("autofarm")
                if hasattr(af, "run_once_now"):
                    af.run_once_now()
                    console.hud("succ", "Фокус вернулся — продолжаю автофарм")
        except Exception:
            pass

        # Макросы — сервис сам продолжит по флагу paused; уведомим HUD
        try:
            if saved_busy.get("macros") and pool_get(self.s, "features.macros.repeat_enabled", False):
                console.hud("succ", "Фокус вернулся — возобновляю повторы макросов")
        except Exception:
            pass
        # Buff/Teleport/Respawn — подхватит пайплайн на ближайшем тике

    # --- rule API ---
    def when(self, snap) -> bool:
        paused = self._is_paused()
        if (not paused) and (snap.is_focused is False) and (snap.focus_unfocused_for_s or 0.0) >= self.grace:
            return True
        if paused and (snap.is_focused is True):
            return True
        return False

    def run(self, snap) -> None:
        paused = self._is_paused()

        if (not paused) and (snap.is_focused is False):
            # ВКЛЮЧИТЬ ПАУЗУ
            saved_enabled = self._save_feature_enabled()
            prev_saved_busy = pool_get(self.s, "runtime.focus_pause.saved_busy", None)
            saved_busy = dict(prev_saved_busy) if prev_saved_busy else self._save_feature_busy()

            # раздать флаги паузы (никаких старт/стоп сервисов)
            self._apply_pause_flags(True, "unfocused")

            # сохранить снимки флагов
            self._set_paused_flag(True, saved_enabled)
            pool_write(self.s, "runtime.focus_pause", {"saved_busy": dict(saved_busy)})

            console.hud("err", "Пауза: окно без фокуса — процессы остановлены")
            return

        if paused and (snap.is_focused is True):
            # СНЯТЬ ПАУЗУ
            saved_enabled = pool_get(self.s, "runtime.focus_pause.saved", {}) or {}
            saved_busy = pool_get(self.s, "runtime.focus_pause.saved_busy", {}) or {}

            # восстановить enabled (бережно), сбросить runtime-флаги
            self._restore_feature_enabled(saved_enabled)
            self._set_paused_flag(False, {})
            pool_write(self.s, "runtime.focus_pause", {"saved_busy": {}})

            # снять 'unfocused'-паузы
            self._apply_pause_flags(False, "unfocused")

            # мягко возобновить то, что действительно было занято
            try:
                self._resume_were_busy(saved_busy)
            except Exception:
                pass

            console.hud("succ", "Фокус вернулся — возобновляем процессы")
