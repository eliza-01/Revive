from __future__ import annotations
from typing import Any, Callable, Dict, Optional
import time

from core.orchestrators.snapshot import Snapshot
from core.engines.respawn.runner import RespawnRunner

# Пытаемся импортировать и фабрику, и класс; фолбэк, если фабрики нет
try:
    from core.engines.respawn.server.boh.engine import create_engine as _create_engine, RespawnEngine
except Exception:
    from core.engines.respawn.server.boh.engine import RespawnEngine  # type: ignore
    _create_engine = None  # фабрики может не быть

class _RespawnRule:
    def __init__(self, sys_state: Dict[str, Any], ps_adapter, controller, report: Callable[[str], None]):
        self.s = sys_state
        self.ps = ps_adapter
        self.controller = controller
        self.report = report
        self._busy_until = 0.0
        self._running = False

        def _is_alive():
            try:
                st = self.ps.last() or {}
                return bool(st.get("alive"))
            except Exception:
                return True

        def _on_engine_report(code: str, text: str):
            self.report(f"[RESPAWN] {text}")
            emit = self.s.get("ui_emit")
            if callable(emit):
                ok = True if code == "SUCCESS" else False if code in ("FAIL","TIMEOUT:CONFIRM","TIMEOUT:WAIT_REBORN") else None
                emit("respawn", text, ok)

        # Создаём движок через фабрику, если она есть; иначе напрямую классом
        if _create_engine:
            self._engine = _create_engine(
                server=self.s.get("server") or "boh",
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=float(self.s.get("respawn_click_threshold", 0.70)),
                confirm_timeout_s=float(self.s.get("respawn_confirm_timeout_s", 6.0)),
                debug=bool(self.s.get("respawn_debug", True)),  # временно True
                on_report=_on_engine_report,
            )
        else:
            self._engine = RespawnEngine(
                server=self.s.get("server") or "boh",
                controller=self.controller,
                is_alive_cb=_is_alive,
                click_threshold=float(self.s.get("respawn_click_threshold", 0.70)),
                confirm_timeout_s=float(self.s.get("respawn_confirm_timeout_s", 6.0)),
                debug=bool(self.s.get("respawn_debug", True)),  # временно True
                on_report=_on_engine_report,
            )

        self._runner = RespawnRunner(
            engine=self._engine,
            get_window=lambda: self.s.get("window"),
            get_language=lambda: self.s.get("language") or "rus",
        )

    def when(self, snap: Snapshot) -> bool:
        now = time.time()
        if now < self._busy_until or self._running:
            return False
        if not snap.has_window:
            return False
        if snap.alive is not False:   # стартуем только если точно мёртв
            return False
        if not bool(self.s.get("respawn_enabled")):
            return False
        return True

    def run(self, snap: Snapshot) -> None:
        self._running = True
        try:
            wait_enabled = bool(self.s.get("respawn_wait_enabled"))
            wait_seconds = int(self.s.get("respawn_wait_seconds", 120))

            if wait_enabled and wait_seconds > 0:
                start = time.time()
                deadline = start + max(0, wait_seconds)
                tick_shown = -1
                while time.time() < deadline:
                    st = self.ps.last() or {}
                    if st.get("alive"):
                        self.report("[RESPAWN] Поднялись сами (ожидание)")
                        emit = self.s.get("ui_emit")
                        if callable(emit):
                            emit("respawn", "Поднялись (ожидание)", True)
                        self._busy_until = time.time() + 2.0
                        return
                    sec = int(time.time() - start)
                    if sec != tick_shown:
                        tick_shown = sec
                        left = max(0, int(deadline - time.time()))
                        self.report(f"[RESPAWN] Ожидание возрождения… {sec}/{wait_seconds} сек (осталось {left})")
                    time.sleep(1.0)

            self.report("[RESPAWN] Активная попытка восстановления…")
            try:
                self._engine.set_server(self.s.get("server") or "boh")
            except Exception:
                pass

            ok = bool(self._runner.run(timeout_ms=14_000))
            self._busy_until = time.time() + (2.0 if ok else 4.0)
        finally:
            self._running = False

def make_respawn_rule(sys_state, ps_adapter, controller, report: Optional[Callable[[str], None]] = None):
    report = report or (lambda _m: None)
    return _RespawnRule(sys_state, ps_adapter, controller, report)
