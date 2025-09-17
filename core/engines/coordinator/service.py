# core/engines/coordinator/service.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import threading
import time

from core.state.pool import pool_get, pool_write
from core.logging import console


class CoordinatorService:
    """
    Централизованный координатор пауз/флагов.
    - Периодически опрашивает providers -> активные причины.
    - Агрегирует их в paused-флаги для features/services/pipeline.
    - НЕ стартует/стопит другие сервисы — только пишет {paused, pause_reason}.

    runtime.pauses.reasons: { <reason>: {active: bool, ts: float} }
    features.<name>.{paused: bool, pause_reason: str}
    services.<name>.{paused: bool, pause_reason: str}
    pipeline.{paused: bool, pause_reason: str, ts: float}
    """

    def __init__(
        self,
        state: Dict,
        *,
        providers: List,
        period_ms: int = 250,
        reason_priority: Tuple[str, ...] = ("ui_guard", "unfocused"),
        features: Tuple[str, ...] = (
            "respawn","buff","macros","teleport","record","autofarm","stabilize","ui_guard"
        ),
        services: Tuple[str, ...] = ("player_state","macros_repeat","autofarm"),
        reason_scopes: Optional[Dict[str, Dict[str, bool]]] = None,
    ):
        self.s = state
        self._providers = list(providers)
        self._period = max(50, int(period_ms))
        self._reason_priority = tuple(reason_priority)
        self._features = tuple(features)
        self._services = tuple(services)
        self._reason_scopes = dict(reason_scopes or {})

        self._thr: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_applied: Dict[str, Dict[str, str | bool]] = {}
        self._last_active_set: set[str] = set()  # ← новое: для pauses.ts

    # ---------- lifecycle ----------
    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._loop, name="CoordinatorService", daemon=True)
        self._thr.start()
        console.log("[coordinator] started")

    def stop(self, timeout: float = 0.5):
        try:
            self._stop.set()
            if self._thr:
                self._thr.join(timeout)
        finally:
            self._thr = None
            console.log("[coordinator] stopped")

    def is_running(self) -> bool:
        return bool(self._thr and self._thr.is_alive())

    # Ручной “тумблер” причин (UI/правила/движки)
    def set_reason_active(self, reason: str, active: bool):
        with self._lock:
            now = time.time()
            self._write_runtime_reason(reason, bool(active), now)
            self._recompute_and_apply(now)

    # ---------- loop ----------
    def _loop(self):
        next_tick = time.time()
        while not self._stop.is_set():
            now = time.time()
            if now >= next_tick:
                try:
                    with self._lock:
                        self._tick(now)
                except Exception as e:
                    console.log(f"[coordinator] loop error: {e}")
                next_tick = now + self._period / 1000.0
            self._stop.wait(0.01)

    def _tick(self, now: float):
        # 1) собрать причины от провайдеров
        for p in self._providers:
            try:
                reason, active = p.evaluate(self.s, now)
                if reason:
                    self._write_runtime_reason(reason, bool(active), now)
            except Exception as e:
                console.log(f"[coordinator] provider error: {e}")
        # 2) применить флаги
        self._recompute_and_apply(now)

    # ---------- reasons ----------
    def _write_runtime_reason(self, reason: str, active: bool, now: float):
        # пишем точечно в конкретный путь, без перезатирания всего runtime.pauses
        path = f"runtime.pauses.reasons.{reason}"
        prev_active = bool(pool_get(self.s, f"{path}.active", False))
        if prev_active == bool(active):
            return
        from core.state.pool import pool_write
        pool_write(self.s, path, {"active": bool(active), "ts": now})

    def _collect_active_reasons(self) -> list[str]:
        reasons_obj = pool_get(self.s, "runtime.pauses.reasons", {}) or {}
        return [r for r, val in reasons_obj.items() if isinstance(val, dict) and val.get("active")]

    def _recompute_and_apply(self, now: float):
        actives = self._collect_active_reasons()
        active_set = set(actives)

        # обновлять runtime.pauses.ts только при изменении совокупности причин
        if active_set != self._last_active_set:
            added = active_set - self._last_active_set
            removed = self._last_active_set - active_set
            # HUD: вход/выход причины 'unfocused'
            try:
                if "unfocused" in added:
                    console.hud("att", "Сервисы остановлены! Вернитесь в Lineage")
                if "unfocused" in removed:
                    console.hud("succ", "Фокус вернулся — возобновляем процессы")
                    console.hud("att", "")
            except Exception:
                pass
            from core.state.pool import pool_write
            pool_write(self.s, "runtime.pauses", {"ts": now})
            self._last_active_set = active_set

        if not actives:
            self._apply_pipeline(False, "")
            self._apply_features(False, "")
            self._apply_services(False, "")
            return

        top_reason = self._select_top_reason(actives)

        # pipeline
        self._apply_pipeline(
            True if self._scope_allows(top_reason, "pipeline") else False,
            top_reason if self._scope_allows(top_reason, "pipeline") else "",
        )

        # features/services (OR по всем активным, но показываем одну top_reason)
        apply_features = any(self._scope_allows(r, "features") for r in actives)
        apply_services = any(self._scope_allows(r, "services") for r in actives)

        self._apply_features(apply_features, top_reason if apply_features else "")
        self._apply_services(apply_services, top_reason if apply_services else "")

    def _select_top_reason(self, actives: List[str]) -> str:
        for r in self._reason_priority:
            if r in actives:
                return r
        return actives[0] if actives else ""

    # ---------- apply ----------
    def _scope_allows(self, reason: str, target_kind: str) -> bool:
        # target_kind in {"features","services","pipeline"}
        sc = self._reason_scopes.get(reason)
        if sc is None:
            return True
        return bool(sc.get(target_kind, False))

    def _apply_pipeline(self, paused: bool, reason: str):
        self._apply_one("pipeline", paused, reason, is_pipeline=True)

    def _apply_features(self, paused: bool, reason: str):
        for fk in self._features:
            self._apply_one(f"features.{fk}", paused, reason)

    def _apply_services(self, paused: bool, reason: str):
        for sk in self._services:
            self._apply_one(f"services.{sk}", paused, reason)

    def _apply_one(self, path_prefix: str, paused: bool, reason: str, *, is_pipeline: bool = False):
        key = ("pipeline" if is_pipeline else path_prefix)
        prev = self._last_applied.get(key) or {}

        cur_paused = bool(pool_get(self.s, f"{path_prefix}.paused", False))
        cur_reason = str(pool_get(self.s, f"{path_prefix}.pause_reason", "") or "")

        new_paused = bool(paused)
        new_reason = str(reason if paused else "")

        if (cur_paused == new_paused and cur_reason == new_reason and
            prev.get("paused") == new_paused and prev.get("pause_reason") == new_reason):
            return

        write_obj = {"paused": new_paused, "pause_reason": new_reason}
        if is_pipeline:
            write_obj["ts"] = time.time()

        pool_write(self.s, path_prefix, write_obj)
        self._last_applied[key] = dict(write_obj)

    # (необязательно) быстрый снэпшот состояния причин
    def reasons_snapshot(self):
        return {
            "reasons": dict(pool_get(self.s, "runtime.pauses.reasons", {}) or {}),
            "pipeline": {
                "paused": bool(pool_get(self.s, "pipeline.paused", False)),
                "reason": str(pool_get(self.s, "pipeline.pause_reason", "") or ""),
            }
        }
