# core/features/flow_orchestrator.py
from __future__ import annotations
import threading
import time
import importlib
from typing import Callable, Optional

from core.runtime.flow_config import PRIORITY
from core.runtime.flow_runner import FlowRunner


class FlowOrchestrator:
    """
    Инкапсулирует весь цикл: баф → макросы → перепроверка → ТП → пост-ТП маршрут,
    а также реакцию на смерть/оживление и единый reset/restart пайплайн.

    Все UI/сервисы прокидываются коллбэками, чтобы разгрузить launcher.py.
    """

    def __init__(
        self,
        *,
        # инфраструктура
        schedule: Callable[[Callable, int], None],     # schedule(fn, delay_ms)
        log: Callable[[str], None] = print,

        # ядро-сервисы
        checker,                   # core.checks.charged.ChargeChecker
        watcher,                   # core.runtime.state_watcher.StateWatcher
        to_village,                # core.features.to_village.ToVillage
        postrow_runner,            # core.features.post_tp_row.PostTPRowRunner
        restart_manager,           # core.features.restart_manager.RestartManager

        # геттеры окружения
        get_server: Callable[[], str],
        get_language: Callable[[], str],
    ):
        self._schedule = schedule
        self._log = log

        self.checker = checker
        self.watcher = watcher
        self.to_village = to_village
        self.postrow = postrow_runner
        self.restart = restart_manager

        self.get_server = get_server
        self.get_language = get_language

        # UI-зависимости (устанавливаются позднее через set_ui())
        self._buff_is_enabled: Callable[[], bool] = lambda: False
        self._buff_run_once: Callable[[], bool] = lambda: False

        self._macros_ui_is_enabled: Callable[[], bool] = lambda: False
        self._macros_ui_run_always: Callable[[], bool] = lambda: False
        self._macros_ui_get_duration_s: Callable[[], float] = lambda: 0.0
        self._macros_run_once: Callable[[], bool] = lambda: False

        self._tp_is_enabled: Callable[[], bool] = lambda: False
        self._tp_teleport_now_selected: Callable[[], bool] = lambda: False
        self._tp_get_selected_destination: Callable[[], tuple[str, str]] = lambda: ("", "")
        self._tp_get_selected_row_id: Callable[[], str] = lambda: ""

        # флаг UI «поднимать после смерти»
        self._respawn_ui_is_enabled: Callable[[], bool] = lambda: False

        # локальные флаги цикла
        self._alive_flag: bool = True
        self._charged_flag: Optional[bool] = None
        self._buff_was_success: bool = False
        self._tp_success: bool = False

        self._tp_after_death = False
        self._revive_decided = True

        self._flow_interrupted = False
        self._cycle_success_marked = False
        self._awaiting_alive_restart = False

        # лимиты reset
        self._fail_streak = 0
        self._max_resets = 3

        # FlowRunner (шаги)
        self.flow = FlowRunner(
            steps={
                "buff_if_needed": self._flow_step_buff_if_needed,
                "macros_after_buff": self._flow_step_macros_after_buff,
                "recheck_charged": self._flow_step_recheck_charged,
                "tp_if_ready": self._flow_step_tp_if_ready,
                "post_tp_row": self._flow_step_post_tp_row,
            },
            order=PRIORITY,
        )

    # ---------------- UI wiring ----------------
    def set_ui(
        self,
        *,
        # баф
        buff_is_enabled: Callable[[], bool],
        buff_run_once: Callable[[], bool],
        # макросы
        macros_ui_is_enabled: Callable[[], bool],
        macros_ui_run_always: Callable[[], bool],
        macros_ui_get_duration_s: Callable[[], float],
        macros_run_once: Callable[[], bool],
        # ТП
        tp_is_enabled: Callable[[], bool],
        tp_teleport_now_selected: Callable[[], bool],
        tp_get_selected_destination: Callable[[], tuple[str, str]],
        tp_get_selected_row_id: Callable[[], str],
        # «в деревню» UI-флаг
        respawn_ui_is_enabled: Callable[[], bool],
    ):
        self._buff_is_enabled = buff_is_enabled
        self._buff_run_once = buff_run_once

        self._macros_ui_is_enabled = macros_ui_is_enabled
        self._macros_ui_run_always = macros_ui_run_always
        self._macros_ui_get_duration_s = macros_ui_get_duration_s
        self._macros_run_once = macros_run_once

        self._tp_is_enabled = tp_is_enabled
        self._tp_teleport_now_selected = tp_teleport_now_selected
        self._tp_get_selected_destination = tp_get_selected_destination
        self._tp_get_selected_row_id = tp_get_selected_row_id

        self._respawn_ui_is_enabled = respawn_ui_is_enabled

    # ---------------- external events (from watcher) ----------------
    def on_dead(self, _st=None):
        self._cycle_success_marked = False
        self._alive_flag = False
        self._charged_flag = None
        self._tp_success = False
        self._log("[state] death detected → charged=None")
        try:
            self.checker.invalidate()
        except Exception:
            pass
        self._log("[state] death detected → charged=None (cache invalidated)")

        try:
            if self._respawn_ui_is_enabled():
                threading.Thread(target=self._raise_after_death, daemon=True).start()
            else:
                self._log("[to_village] skipped (UI disabled or missing)")
        except Exception as e:
            self._log(f"[to_village] error: {e}")

    def on_alive(self, _st=None):
        self._alive_flag = True
        ch = self.checker.is_charged(None)
        self._charged_flag = ch
        self._log(f"[state] alive detected → charged={ch}")
        self._schedule(self.run_cycle, 0)

    # ---------------- cycle runner ----------------
    def run_cycle(self):
        # не перезапускать завершённый цикл без триггера
        if self._cycle_success_marked and not self._flow_interrupted:
            self._log("[flow] skip: cycle already completed, waiting for next trigger")
            return
        # если мёртв — ждём оживления, не плодя таймеры
        if not self.watcher.is_alive():
            self._log("[flow] waiting alive to restart cycle…")
            self._awaiting_alive_restart = True
            self._schedule(self.run_cycle, 1000)
            return

        # если включён «подъём после смерти» — ждём решения, кто поднял
        if self._respawn_ui_is_enabled() and not getattr(self, "_revive_decided", True):
            self._log("[flow] revive in progress, waiting…")
            self._awaiting_alive_restart = True
            self._schedule(self.run_cycle, 300)
            return

        # старт цикла
        self._awaiting_alive_restart = False
        if self._flow_interrupted:
            self._flow_interrupted = False

        self._buff_was_success = False
        self._cycle_success_marked = False
        self.flow.run()

    # ---------------- flow steps ----------------
    def _flow_step_buff_if_needed(self):
        if not self.watcher.is_alive():
            self._log("[buff] skip (dead)")
            self._buff_was_success = False
            return

        charged_now = bool(self.checker.is_charged(None))
        buff_enabled = bool(self._buff_is_enabled())
        need_buff = buff_enabled and not charged_now

        if need_buff:
            ok_buff = bool(self._buff_run_once())
            self._log(f"[buff] auto-after-alive run: {ok_buff}")
            self._buff_was_success = ok_buff
        else:
            reason = "disabled" if not buff_enabled else "already charged"
            self._log(f"[buff] skip ({reason})")
            self._buff_was_success = False

    def _flow_step_macros_after_buff(self):
        try:
            if not self._macros_ui_is_enabled():
                self._log("[macros] skipped (UI disabled)")
                return
            if not self._buff_was_success and not self._macros_ui_run_always():
                self._log("[macros] skipped (buff not executed, run_always=False)")
                return

            ok_macros = bool(self._macros_run_once())
            try:
                dur = float(self._macros_ui_get_duration_s())
            except Exception:
                dur = 0.0
            if dur > 0:
                self._log(f"[macros] waiting {dur:.2f}s for completion window")
                time.sleep(dur)
            self._log(f"[macros] after-buff run: {ok_macros}")
        except Exception as e:
            self._log(f"[macros] error: {e}")

    def _flow_step_recheck_charged(self):
        try:
            v = self.checker.force_check()
            self._charged_flag = bool(v)
            self._log(f"[flow] recheck_charged → {v}")
        except Exception as e:
            self._log(f"[flow] recheck_charged error: {e}")

    def _flow_step_tp_if_ready(self):
        tp_enabled = bool(self._tp_is_enabled())
        if not tp_enabled:
            self._log("[flow] tp_if_ready → skip (disabled)")
            self._tp_success = False
            self._mark_cycle_success("tp_disabled")
            return

        if self._charged_flag is not True:
            self._log(f"[flow] tp_if_ready → skip (not charged: {self._charged_flag})")
            self._tp_success = False
            self._reset_and_run(reason="not_charged_for_tp")
            return

        self._tp_success = bool(self._tp_teleport_now_selected())
        self._log(f"[flow] tp_if_ready → {self._tp_success}")
        self._tp_after_death = False

        if not self._tp_success:
            self._reset_and_run(reason="tp_failed")
            return

        if self._tp_success and not self._is_row_selected():
            self._mark_cycle_success("tp_only")

    def _flow_step_post_tp_row(self):
        try:
            if not self._tp_success:
                self._log("[rows] skip (tp not successful)")
                return

            cat, loc = self._tp_get_selected_destination()
            row_id = self._tp_get_selected_row_id()

            if not (cat and loc):
                self._log("[rows] no destination → treat as success")
                self._mark_cycle_success("tp_only")
                return

            if not row_id:
                self._log("[rows] no row selected → treat as success")
                self._mark_cycle_success("tp_no_row")
                return

            ok = bool(self.postrow.run_row(cat, loc, row_id))
            self._log(f"[rows] run → {ok}")
            if ok:
                self._mark_cycle_success("post_tp_row")
            else:
                self._reset_and_run("row_failed")
        except Exception as e:
            self._log(f"[rows] error: {e}")
            self._reset_and_run("row_exception")
        finally:
            self._tp_success = False

    # --- хуки автофарма ---
    def set_autofarm_start(self, start_fn):
        """Передай сюда функцию, которая реально запускает автофарм."""
        self._af_start_fn = start_fn

    def step_autofarm_after_rows(self):
        """Шаг после маршрута: старт автофарма (если хук задан)."""
        fn = getattr(self, "_af_start_fn", None)
        if not callable(fn):
            self._log("[orch] autofarm hook not set; skip")
            return
        try:
            ok = bool(fn())
            self._log(f"[orch] autofarm start → {'OK' if ok else 'FAIL'}")
        except Exception as e:
            self._log(f"[orch] autofarm start error: {e}")

    # ---------------- helpers ----------------
    def _raise_after_death(self):
        try:
            ok = bool(self.to_village.run_once(timeout_ms=4000))
            self._log(f"[to_village] run: {ok}")
            self._tp_after_death = ok
            if not ok:
                self._reset_and_run(reason="to_village_failed")
        except Exception as e:
            self._log(f"[to_village] error in thread: {e}")
            self._tp_after_death = False
        finally:
            self._revive_decided = True

    def _is_row_selected(self) -> bool:
        try:
            return bool(self._tp_get_selected_row_id())
        except Exception:
            return False

    def _mark_cycle_success(self, where: str):
        if self._fail_streak:
            self._log(f"[reset] success at {where} → streak 0")
        self._fail_streak = 0
        self._flow_interrupted = False
        self._cycle_success_marked = True

    # ---------------- reset / restart orchestration ----------------
    def _reset_and_run(self, reason: str = "unknown"):
        """
        Увеличить счётчик провалов, выполнить dashboard_reset и перезапустить цикл.
        После превышения лимита — вызвать restart_account().
        """
        next_fail = self._fail_streak + 1
        if next_fail >= self._max_resets:
            self._fail_streak = self._max_resets
            self._log(f"[reset] reason={reason}, streak={self._fail_streak}/{self._max_resets} (limit)")
            self._log("[reset] max attempts reached → restart_account()")
            ok = self.restart.restart_account(on_progress=self._log)
            if ok:
                # watcher уже перезапущен внутри restart_manager
                self._fail_streak = 0
                self._flow_interrupted = False
                self._cycle_success_marked = False
                self._schedule(self.run_cycle, 0)
            return

        self._fail_streak = next_fail
        self._log(f"[reset] reason={reason}, streak={self._fail_streak}/{self._max_resets}")

        # 1) мягкий сброс дашборда
        try:
            self.restart.run_dashboard_reset()
        except Exception as e:
            self._log(f"[reset] dashboard_reset error: {e}")

        # 2) если всё ещё мёртвы — повторно «В деревню»
        try:
            if not self.watcher.is_alive() and self._respawn_ui_is_enabled():
                self._revive_decided = False
                self._log("[reset] still dead → retry ToVillage")
                threading.Thread(target=self._raise_after_death, daemon=True).start()
        except Exception as e:
            self._log(f"[reset] revive retry error: {e}")

        # 3) метки и перезапуск цикла
        self._tp_success = False
        self._buff_was_success = False
        self._flow_interrupted = True
        if not self._awaiting_alive_restart:
            self._awaiting_alive_restart = True
            self._schedule(self.run_cycle, 0)
