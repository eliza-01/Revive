# core/engines/respawn/server/boh/orchestrator_rules.py
from __future__ import annotations
from typing import Any, Dict, Optional

from core.orchestrators.rules_base import Rule
from core.engines.respawn.server.boh.engine import create_engine
from core.engines.respawn.runner import RespawnRunner

class RespawnRule(Rule):
    """
    Тригерится, когда игрок мёртв и респавн включён.
    Делегирует работу движку respawn (с on_report → в UI статус 'respawn').
    """
    def __init__(self, sys_state: Dict[str, Any], watcher, controller):
        self.s = sys_state
        self.watcher = watcher
        self.controller = controller
        self._busy = False

    # условие срабатывания
    def when(self, snap) -> bool:
        if self._busy:
            return False
        if not snap.has_window:
            return False
        if snap.alive is None:
            return False
        if snap.alive is True:
            return False
        if not bool(self.s.get("respawn_enabled", False)):
            return False
        return True

    def run(self, snap) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            # актуальные параметры
            mode = "wait_reborn" if self.s.get("respawn_wait_enabled") else "auto"
            wait_sec = int(self.s.get("respawn_wait_seconds", 120)) if mode == "wait_reborn" else 0
            click_thr = float(self.s.get("respawn_click_threshold", 0.70))
            confirm_to = float(self.s.get("respawn_confirm_timeout_s", 6.0))

            # on_report → проброс в UI
            def _emit(code: str, text: str):
                ui_emit = self.s.get("ui_emit")
                if callable(ui_emit):
                    # ok только на финалах SUCCESS/FAIL, остальное — нейтрально
                    ok = True if code == "SUCCESS" else False if code == "FAIL" else None
                    ui_emit("respawn", text, ok)

            engine = create_engine(
                server=self.s.get("server", "boh"),
                controller=self.controller,
                is_alive_cb=lambda: self.watcher.is_alive(),
                click_threshold=click_thr,
                confirm_timeout_s=confirm_to,
                debug=True,
                on_report=_emit,
            )
            runner = RespawnRunner(
                engine=engine,
                get_window=lambda: self.s.get("window"),
                get_language=lambda: self.s.get("language", "rus"),
            )

            ok = runner.run(mode=mode, wait_seconds=wait_sec, total_timeout_ms=20_000)
            # можно сохранить результат для следующих правил (ТП/баф/АФ)
            self.s["_last_respawn_ok"] = bool(ok)

        except Exception as e:
            ui_emit = self.s.get("ui_emit")
            if callable(ui_emit):
                ui_emit("respawn", f"[respawn] ошибка: {e}", False)
        finally:
            self._busy = False


def make_respawn_rule(sys_state, watcher, controller) -> RespawnRule:
    return RespawnRule(sys_state, watcher, controller)
