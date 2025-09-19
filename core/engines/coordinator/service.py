# core/engines/coordinator/service.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Set, Callable
import threading
import time

from core.state.pool import pool_get, pool_write
from core.logging import console


class CoordinatorService:
    """
    Централизованный координатор пауз/флагов (только cor_1 и cor_2).

    Семантика:
      - cor_1 (unfocused):
          * запоминаем тех, кого САМИ поставили на паузу (pipeline + features + services, кроме ui_guard),
            и снимаем паузы только с них, когда причина уходит (фокус вернулся).
      - cor_2 (alive=True, hp=None, autofarm.busy=True):
          * ставим на паузу всех (кроме ui_guard) по той же схеме ведёрка;
          * гарантированно запускаем ui_guard через колбэк ensure_ui_guard_watch();
          * когда ui_guard завершился:
              - если pause_reason == "empty" → снимаем паузы только у тех, кого ставили под cor_2;
              - если pause_reason непустая → показываем HUD-заглушку и паузы ДЕРЖИМ.
    """

    def __init__(
        self,
        state: Dict,
        *,
        period_ms: int = 500,
        providers: List,
        reason_priority: Tuple[str, ...] = ("cor_2", "cor_1"),
        # ui_guard специально НЕ включаем в features
        features: Tuple[str, ...] = (
            "respawn","buff","macros","teleport","record","autofarm","stabilize"
        ),
        services: Tuple[str, ...] = ("player_state","macros_repeat","autofarm"),
        reason_scopes: Optional[Dict[str, Dict[str, bool]]] = None,
        # колбэки для управления ui_guard
        ensure_ui_guard_watch: Optional[Callable[[], bool]] = None,
        ui_guard_is_busy: Optional[Callable[[], bool]] = None,
        stop_ui_guard_watch: Optional[Callable[[], bool]] = None,
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

        # ведёрки: кого САМИ тормознули по cor_1 / cor_2
        self._granted_by: Dict[str, Set[str]] = {"cor_1": set(), "cor_2": set()}
        self._last_active_set: set[str] = set()

        # HUD анти-дребезг для cor_1
        self._hud_flags: Dict[str, bool] = {"cor1_shown_stop": False, "cor1_shown_resume": False}

        # управление ui_guard
        self._ensure_ui_guard_watch = ensure_ui_guard_watch
        self._ui_guard_is_busy = ui_guard_is_busy
        self._stop_ui_guard_watch = stop_ui_guard_watch

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

    # Ручной “тумблер” причины (если понадобится)
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
        # 2) применить флаги — новой семантикой
        self._recompute_and_apply(now)

    # ---------- reasons ----------
    def _write_runtime_reason(self, reason: str, active: bool, now: float):
        path = f"runtime.pauses.reasons.{reason}"
        prev_active = bool(pool_get(self.s, f"{path}.active", False))
        if prev_active == bool(active):
            return
        pool_write(self.s, path, {"active": bool(active), "ts": now})

    def _collect_active_reasons(self) -> list[str]:
        reasons_obj = pool_get(self.s, "runtime.pauses.reasons", {}) or {}
        return [r for r, val in reasons_obj.items() if isinstance(val, dict) and val.get("active")]

    # ---------- apply helpers ----------
    def _all_targets(self) -> List[str]:
        paths: List[str] = []
        paths.append("pipeline")
        for f in self._features:
            paths.append(f"features.{f}")
        for s in self._services:
            paths.append(f"services.{s}")
        return paths

    def _apply_one(self, path_prefix: str, paused: bool, reason: str, *, is_pipeline: bool = False):
        cur_paused = bool(pool_get(self.s, f"{path_prefix}.paused", False)) if not is_pipeline \
                     else bool(pool_get(self.s, "pipeline.paused", False))
        cur_reason = str(pool_get(self.s, f"{path_prefix}.pause_reason", "") or "") if not is_pipeline \
                     else str(pool_get(self.s, "pipeline.pause_reason", "") or "")

        new_paused = bool(paused)
        new_reason = str(reason if paused else "")

        write_obj: Dict[str, object] = {"paused": new_paused, "pause_reason": new_reason}
        if is_pipeline:
            write_obj["ts"] = time.time()

        if (cur_paused == write_obj.get("paused", cur_paused)) and (cur_reason == write_obj.get("pause_reason", cur_reason)):
            return

        pool_write(self.s, path_prefix, write_obj)

    def _ensure_paused_for_reason(self, reason: str):
        bucket = self._granted_by.setdefault(reason, set())
        for path in self._all_targets():
            # не трогаем уже приостановленные (мы их не ставили)
            cur_paused = bool(pool_get(self.s, f"{path}.paused", False)) if path != "pipeline" \
                         else bool(pool_get(self.s, "pipeline.paused", False))
            if cur_paused:
                continue
            self._apply_one(path, paused=True, reason=reason, is_pipeline=(path == "pipeline"))
            bucket.add(path)

    def _release_paused_for_reason(self, reason: str):
        bucket = self._granted_by.setdefault(reason, set())
        for path in list(bucket):
            self._apply_one(path, paused=False, reason="", is_pipeline=(path == "pipeline"))
            bucket.discard(path)

    # ---------- recompute ----------
    def _recompute_and_apply(self, now: float):
        actives = set(self._collect_active_reasons())

        # HUD вход/выход для cor_1
        if actives != self._last_active_set:
            added = actives - self._last_active_set
            removed = self._last_active_set - actives
            try:
                if "cor_1" in added and not self._hud_flags.get("cor1_shown_stop"):
                    console.hud("att", "Сервисы остановлены! Вернитесь в Lineage")
                    self._hud_flags["cor1_shown_stop"] = True
                    self._hud_flags["cor1_shown_resume"] = False
                if "cor_1" in removed and not self._hud_flags.get("cor1_shown_resume"):
                    console.hud("succ", "Фокус вернулся — возобновляем процессы")
                    console.hud("att", "")
                    self._hud_flags["cor1_shown_resume"] = True
                    self._hud_flags["cor1_shown_stop"] = False
            except Exception:
                pass
            pool_write(self.s, "runtime.pauses", {"ts": now})
            self._last_active_set = set(actives)

        # --- cor_1: unfocused ---
        if "cor_1" in actives:
            self._ensure_paused_for_reason("cor_1")
        else:
            self._release_paused_for_reason("cor_1")

        # --- cor_2: hp=None при alive и активном autofarm ---
        if "cor_2" in actives:
            # ставим паузы всем (кроме самого ui_guard, которого нет в features)
            self._ensure_paused_for_reason("cor_2")

            # 1) если ui_guard не занят — запускаем его
            try:
                is_busy = self._ui_guard_is_busy() if self._ui_guard_is_busy \
                    else bool(pool_get(self.s, "features.ui_guard.busy", False))
            except Exception:
                is_busy = bool(pool_get(self.s, "features.ui_guard.busy", False))

            if not is_busy and self._ensure_ui_guard_watch:
                try:
                    started = bool(self._ensure_ui_guard_watch())
                    if not started:
                        console.log("[coordinator] ensure_ui_guard_watch() returned False")
                except Exception as e:
                    console.log(f"[coordinator] ensure_ui_guard_watch error: {e}")

            # 2) если ui_guard уже завершился — смотрим итог и останавливаем watch
            try:
                busy_now = self._ui_guard_is_busy() if self._ui_guard_is_busy \
                    else bool(pool_get(self.s, "features.ui_guard.busy", False))
                if not busy_now:
                    reason = str(pool_get(self.s, "features.ui_guard.pause_reason", "") or "").lower().strip()
                    if reason in ("", "empty"):
                        self._release_paused_for_reason("cor_2")
                    else:
                        console.hud("att", reason)
                    try:
                        if self._stop_ui_guard_watch:
                            self._stop_ui_guard_watch()
                        pool_write(self.s, "features.ui_guard", {"watching": False})
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            # причина ушла — отпускаем только наш bucket
            self._release_paused_for_reason("cor_2")

            # защита: если ui_guard всё ещё крутится — мягко остановим watch
            try:
                still_busy = self._ui_guard_is_busy() if self._ui_guard_is_busy \
                    else bool(pool_get(self.s, "features.ui_guard.busy", False))
            except Exception:
                still_busy = bool(pool_get(self.s, "features.ui_guard.busy", False))

            try:
                watching = bool(pool_get(self.s, "features.ui_guard.watching", False))
            except Exception:
                watching = False

            if (still_busy or watching) and self._stop_ui_guard_watch:
                try:
                    self._stop_ui_guard_watch()
                    pool_write(self.s, "features.ui_guard", {"watching": False})
                except Exception:
                    pass

    def _select_top_reason(self, actives: List[str]) -> str:
        for r in self._reason_priority:
            if r in actives:
                return r
        return actives[0] if actives else ""

    # ---------- debug ----------
    def reasons_snapshot(self):
        return {
            "reasons": dict(pool_get(self.s, "runtime.pauses.reasons", {}) or {}),
            "pipeline": {
                "paused": bool(pool_get(self.s, "pipeline.paused", False)),
                "reason": str(pool_get(self.s, "pipeline.pause_reason", "") or ""),
            }
        }
