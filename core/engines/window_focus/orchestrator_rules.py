# core/engines/window_focus/orchestrator_rules.py
from __future__ import annotations
from typing import Any, Callable, Dict, Optional
import time

def make_focus_pause_rule(sys_state: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None):
    """
    Пауза всех процессов, если окно без фокуса дольше grace_seconds.
    При возврате фокуса — восстановить сохранённые флаги.
    Дополнительно: останавливаем/запускаем сервис чтения HP.
    """
    return _FocusPauseRule(sys_state, cfg or {})

class _FocusPauseRule:
    def __init__(self, sys_state: Dict[str, Any], cfg: Dict[str, Any]):
        self.s = sys_state
        self.grace = float(cfg.get("grace_seconds", 1.0))  # по ТЗ — секунда
        self.key = "_focus_pause"  # {"active":bool, "saved":{...}}

    def when(self, snap) -> bool:
        paused = bool(self.s.get(self.key, {}).get("active"))
        # активироваться: не на паузе и без фокуса ≥ grace
        if (not paused) and (snap.has_focus is False) and (snap.focus_unfocused_for_s or 0) >= self.grace:
            return True
        # снять паузу: пауза активна и фокус вернулся
        if paused and (snap.has_focus is True):
            return True
        return False

    def run(self, snap) -> None:
        paused = bool(self.s.get(self.key, {}).get("active"))
        ui_emit: Optional[Callable[[str, str, Optional[bool]], None]] = self.s.get("ui_emit")
        services = self.s.get("_services") or {}
        ps_service = services.get("player_state")

        if (not paused) and (snap.has_focus is False):
            # ВКЛЮЧИТЬ ПАУЗУ
            saved = {
                "af_enabled":        bool(self.s.get("af_enabled", False)),
                "respawn_enabled":   bool(self.s.get("respawn_enabled", False)),
                "buff_enabled":      bool(self.s.get("buff_enabled", False)),
                "macros_enabled":    bool(self.s.get("macros_enabled", False)),
                "tp_enabled":        bool(self.s.get("tp_enabled", False)),
            }

            # стоп HP-сенсор
            try:
                if ps_service and ps_service.is_running():
                    ps_service.stop()
            except Exception:
                pass

            # ⬇️ Новое: явный сброс состояния HP в "unknown"
            self.s["_ps_last"] = {
                "alive": None,
                "hp_ratio": None,
                "cp_ratio": None,
                "ts": time.time(),
            }

            self.s[self.key] = {"active": True, "saved": saved}

            try:
                if callable(ui_emit):
                    ui_emit("postrow", "Пауза: окно без фокуса — процессы остановлены", None)
            except Exception:
                pass
            return

        if paused and (snap.has_focus is True):
            # СНЯТЬ ПАУЗУ
            saved = (self.s.get(self.key) or {}).get("saved", {})
            # Не затираем изменения, сделанные во время паузы (например, включили тумблер)

            for k, v in saved.items():
                cur = bool(self.s.get(k, False))
                self.s[k] = bool(v) or cur
            self.s[self.key] = {"active": False, "saved": {}}

            # перезапуск HP-сенсора
            try:
                if ps_service and not ps_service.is_running():
                    ps_service.start()
            except Exception:
                pass

            try:
                if callable(ui_emit):
                    ui_emit("postrow", "Фокус вернулся — возобновляем процессы", True)
            except Exception:
                pass
