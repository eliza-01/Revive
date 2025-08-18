# app/launcher.py
from __future__ import annotations
import traceback
import sys
import threading
import tkinter as tk
import tkinter.ttk as ttk
import logging
import time  # ← вот это
import importlib

from core.connection import ReviveController
from core.connection_test import run_test_command

from core.servers.registry import get_server_profile
from core.servers.l2mad.flows.rows.registry import list_rows

from core.runtime.state_watcher import StateWatcher
from core.runtime.poller import RepeaterThread
from core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

# from core.features.auto_respawn_runner import AutoRespawnRunner
from core.features.to_village import ToVillage
from core.features.afterbuff_macros import AfterBuffMacroRunner
from core.features.post_tp_row import PostTPRowRunner
from core.features.dashboard_reset import DashboardResetRunner


from core.checks.charged import ChargeChecker, BuffTemplateProbe

from app.ui.window_probe import WindowProbe
from app.ui.state_controls import StateControls
from app.ui.respawn_controls import RespawnControls
from app.ui.buff_controls import BuffControls
from app.ui.tp_controls import TPControls
from app.ui.updater_dialog import run_update_check
from app.ui.settings import BuffIntervalControl
from app.ui.afterbuff_macros import AfterBuffMacrosControls

from core.runtime.flow_config import PRIORITY
from core.runtime.flow_runner import FlowRunner


class _Collapsible(tk.Frame):
    def __init__(self, parent, title: str, opened: bool = True):
        super().__init__(parent)
        self._open = tk.BooleanVar(value=opened)
        self._btn = ttk.Button(self, text=("▼ " + title if opened else "► " + title), command=self._toggle)
        self._btn.pack(fill="x", pady=(6, 2))
        self._body = tk.Frame(self)
        if opened:
            self._body.pack(fill="x")

    def _toggle(self):
        if self._open.get():
            self._open.set(False)
            self._btn.config(text="► " + self._btn.cget("text")[2:])
            self._body.forget()
        else:
            self._open.set(True)
            self._btn.config(text="▼ " + self._btn.cget("text")[2:])
            self._body.pack(fill="x")

    def body(self) -> tk.Frame:
        return self._body


# ---------------- Logging ----------------
def _init_logging():
    LOG_PATH = "revive.log"
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s")
    return LOG_PATH


_init_logging()


class ReviveLauncherUI:
    def __init__(self, root: tk.Tk):
        self.root = root

        # --- state ---
        self.language = "rus"
        self.language_var = tk.StringVar(value=self.language)
        self.server = "l2mad"
        self.server_var = tk.StringVar(value=self.server)

        self._alive_flag = True
        self._charged_flag = None  # None/False/True

        # --- controller ---
        self.controller = ReviveController()

        # --- server profile FIRST ---
        self.profile = get_server_profile(self.server)

        # --- post-TP rows UI state ---
        self._row_var = tk.StringVar(value="")
        self._rows_menu: ttk.Combobox | None = None
        self._rows_cache: list[tuple[str, str]] = []   # [(id, title)]
        self._last_row_dest = ("", "")                 # (village_id, location_id)

        self.checker = ChargeChecker(interval_minutes=10, mode="ANY")
        self.checker.register_probe(
            "autobuff_icons",
            BuffTemplateProbe(
                name="autobuff_icons",
                server_getter=lambda: self.server,
                get_window=lambda: self._safe_window(),
                get_language=lambda: self.language,
                zone_key="buff_bar",
                tpl_keys=[
                    "buff_icon_shield",
                    "buff_icon_blessedBody",
                ],
                threshold=0.85,
                debug=True,
            ),
            enabled=True,
        )

        self.postrow = PostTPRowRunner(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            on_status=lambda msg, ok: print(msg),
        )

        # агрегатор «заряженности» (заглушка проверки)
        def _probe_is_buffed_stub() -> bool:
            return False

        # флаг и поллер для автобафов по интервалу
        self._autobuff_enabled = False
        self.charge_poller = RepeaterThread(fn=self._buff_interval_tick, interval=1.0, debug=False)
        self.charge_poller.start()  # тикает всегда; действует только при включённом флаге

        # исполнитель «В деревню»
        self.to_village = ToVillage(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            click_threshold=0.87,
            debug=True,
            is_alive=lambda: self.watcher.is_alive(),
            confirm_timeout_s=3.0,
        )
        self._tp_after_death = False  # ТП запускать только если мы жали "В деревню"

        # --- periodic buff tick placeholder (профильный) ---
        self.buff_runner = None
        if hasattr(self.profile, "buff_tick"):
            self.buff_runner = RepeaterThread(
                fn=lambda: self.profile.buff_tick(self._safe_window(), self.controller, language=self.language, debug=True),
                interval=15.0,
                debug=False,
            )

        # раннер макросов создадим позже, когда UI будет
        self.afterbuff_ui = None
        self.afterbuff_runner = None

        self._tp_success = False

        # --- window probe ---
        self.winprobe = WindowProbe(root=self.root, on_found=self._on_window_found)

        # --- watcher: только мониторинг состояния ---
        self.watcher = StateWatcher(
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            poll_interval=0.2,
            zero_hp_threshold=0.01,
            on_state=self._on_state_ui,
            on_dead=self._on_dead_ui,
            on_alive=self._on_alive_ui,
            debug=True,
        )

        # --- ui parts ---
        self.driver_status = None
        self.version_status_label = None

        self.flow = FlowRunner(
            steps={
                "buff_if_needed": self._flow_step_buff_if_needed,
                "macros_after_buff": self._flow_step_macros_after_buff,
                "recheck_charged": self._flow_step_recheck_charged,
                "tp_if_ready": self._flow_step_tp_if_ready,
                "post_tp_row": self._flow_step_post_tp_row,  # ←
            },
            order=PRIORITY,
        )

        #reset_and_run
        self._tp_success = False

        # ── NEW: счётчик подряд неудачных циклов и лимит
        self._fail_streak = 0
        self._max_resets = 3
        self._flow_interrupted = False
        self._cycle_success_marked = False

        self._reset_in_progress = False
        self._awaiting_alive_restart = False
        # ---------------------------------------------------------------------

        # --- window probe ---
        self.winprobe = WindowProbe(root=self.root, on_found=self._on_window_found)

        # ping arduino
        try:
            self.controller.send("ping")
            response = self.controller.read()
            print("[✓] Arduino ответила" if response == "pong" else "[×] Нет ответа")
        except Exception as e:
            print(f"[×] Ошибка связи с Arduino: {e}")

        self.update_window_ref = None

    # ----------------  Charge Flow  ----------------
    def _flow_step_buff_if_needed(self):
        # ← новый гард
        if not self.watcher.is_alive():
            print("[buff] skip (dead)")
            self._buff_was_success = False
            return

        charged_now = bool(self.checker.is_charged(None))
        buff_enabled = getattr(self.buff, "is_enabled", lambda: False)()
        need_buff = buff_enabled and not charged_now

        if need_buff:
            ok_buff = self.buff.run_once()
            print(f"[buff] auto-after-alive run: {ok_buff}")
            self._buff_was_success = ok_buff
        else:
            reason = "disabled" if not buff_enabled else "already charged"
            print(f"[buff] skip ({reason})")
            self._buff_was_success = False

    def _flow_step_macros_after_buff(self):
        try:
            # если UI выключен — сразу завершаем шаг
            if not self.afterbuff_ui.is_enabled():
                self._macros_done = True
                print("[macros] skipped (UI disabled)")
                return

            # проверка: либо баф был, либо разрешено запускать без бафа
            if not self._buff_was_success and not self.afterbuff_ui.run_always():
                self._macros_done = True
                print("[macros] skipped (buff not executed, run_always=False)")
                return

            ok_macros = self.afterbuff_runner.run_once()

            try:
                dur = float(self.afterbuff_ui.get_duration_s())
            except Exception:
                dur = 0.0

            if dur > 0:
                print(f"[macros] waiting {dur:.2f}s for completion window")
                time.sleep(dur)

            self._macros_done = True
            print(f"[macros] after-buff run: {ok_macros}")

        except Exception as e:
            self._macros_done = True
            print(f"[macros] error: {e}")

    def _flow_step_recheck_charged(self):
        try:
            v = self.checker.force_check()
            self._charged_flag = bool(v)
            print(f"[flow] recheck_charged → {v}")
        except Exception as e:
            print(f"[flow] recheck_charged error: {e}")

    def _flow_step_tp_if_ready(self):
        tp_enabled = getattr(self.tp, "is_enabled", lambda: False)()
        if not tp_enabled:
            print("[flow] tp_if_ready → skip (disabled)")
            self._tp_success = False
            self.reset_and_run("tp_disabled")
            return

        if self._charged_flag is not True:
            print(f"[flow] tp_if_ready → skip (not charged: {self._charged_flag})")
            self._tp_success = False
            self.reset_and_run("not_charged_for_tp")
            return

        self._tp_success = False  # сброс перед попыткой
        fn = getattr(self.tp, "teleport_now_selected", None)
        ok_tp = bool(fn()) if callable(fn) else False
        self._tp_success = ok_tp
        print(f"[flow] tp_if_ready → {ok_tp}")

        if not ok_tp:
            self.reset_and_run("tp_failed")
            return

        if ok_tp and not self._is_row_selected():
            self._mark_cycle_success("tp_only")

        self._tp_after_death = False

    def _flow_step_post_tp_row(self):
        try:
            if not getattr(self, "_tp_success", False):
                print("[rows] skip (tp not successful)")
                return

            get_sel = getattr(self.tp, "get_selected_destination", None)
            get_row = getattr(self.tp, "get_selected_row_id", None)
            if not callable(get_sel) or not callable(get_row):
                print("[rows] UI does not expose selection")
                return

            cat, loc = get_sel()
            row_id = get_row()

            if not (cat and loc):
                print("[rows] no destination → treat as success")
                self._mark_cycle_success("tp_only")
                return

            if not row_id:
                print("[rows] no row selected → treat as success")
                self._mark_cycle_success("tp_no_row")
                return

            ok = self.postrow.run_row(cat, loc, row_id)
            print(f"[rows] run → {ok}")
            if ok:
                self._mark_cycle_success("post_tp_row")
            else:
                self.reset_and_run("row_failed")
        except Exception as e:
            print(f"[rows] error: {e}")
            self.reset_and_run("row_exception")
        finally:
            self._tp_success = False


    # ----------------  Buff Interval Checker ----------------
    def _buff_interval_tick(self):
        # работает только при включённом флаге и когда живы
        if not self._autobuff_enabled or not getattr(self, "_alive_flag", True):
            return
        try:
            # опрос по интервалу; если рано — выходим
            if not self.checker.tick():
                return

            cur = self.checker.is_charged(None)
            print(f"[charged] interval → {cur}")
            if cur is True:
                self._charged_flag = True
                return  # уже заряжены

            # cur is False/None → пробуем баф
            if getattr(self.buff, "is_enabled", lambda: False)():
                ok = self.buff.run_once()
                print(f"[buff] interval autobuff run: {ok}")
                if ok:
                    # мгновенная переоценка и обновление локального флага
                    new_val = self.checker.force_check()
                    self._charged_flag = bool(new_val)
                    print(f"[charged] after buff → {new_val}")
        except Exception as e:
            print(f"[buff] interval tick error: {e}")

    # ----------------  State Watcher ----------------
    def _on_state_ui(self, st):
        pass

    def _raise_after_death(self):
        try:
            ok = self.to_village.run_once(timeout_ms=4000)
            print(f"[to_village] run: {ok}")
            self._tp_after_death = bool(ok)
            if not ok:
                # <<< важно: тянем общий ресет
                self.reset_and_run(reason="to_village_failed")
        except Exception as e:
            print(f"[to_village] error in thread: {e}")
            self._tp_after_death = False
        finally:
            self._revive_decided = True

    def _on_dead_ui(self, st):
        self._alive_flag = False
        self._charged_flag = None
        self._tp_success = False
        print("[state] death detected → charged=None")
        try:
            self.checker.invalidate()  # ← ВАЖНО: сбросить кеш при смерти
        except Exception:
            pass
        print("[state] death detected → charged=None (cache invalidated)")
        try:
            ui_ok = (
                    getattr(self, "respawn_ui", None)
                    and getattr(self.respawn_ui, "is_enabled", None)
                    and self.respawn_ui.is_enabled()
            )
            if ui_ok:
                threading.Thread(target=self._raise_after_death, daemon=True).start()
            else:
                print("[to_village] skipped (UI disabled or missing)")
        except Exception as e:
            print(f"[to_village] error: {e}")

    def _on_alive_ui(self, st):
        self._alive_flag = True
        ch = self.checker.is_charged(None)
        self._charged_flag = ch
        print(f"[state] alive detected → charged={ch}")
        try:
            self.root.after(0, self._run_alive_flow)
        except Exception:
            self._run_alive_flow()

    def _run_alive_flow(self):
        # если мёртв — ждём оживления, не плодя таймеры
        if not self.watcher.is_alive():
            print("[flow] waiting alive to restart cycle…")
            self._awaiting_alive_restart = True
            try:
                self.root.after(1000, self._run_alive_flow)
            except Exception:
                time.sleep(1); self._run_alive_flow()
            return

        # если включён «подъём после смерти» — ждём решения, кто поднял
        try:
            ui_wants_raise = getattr(self, "respawn_ui", None) and self.respawn_ui.is_enabled()
        except Exception:
            ui_wants_raise = False

        if ui_wants_raise and not getattr(self, "_revive_decided", True):
            print("[flow] revive in progress, waiting…")
            self._awaiting_alive_restart = True
            try:
                self.root.after(300, self._run_alive_flow)
            except Exception:
                time.sleep(0.3); self._run_alive_flow()
            return

        # стартуем цикл (очищаем ожидание)
        self._awaiting_alive_restart = False
        if self._flow_interrupted:
            self._flow_interrupted = False

        self._buff_was_success = False
        self._cycle_success_marked = False
        self.flow.run()

    # resets restarts
    def reset_and_run(self, reason: str = "unknown"):
        """Единая точка восстановления: увеличить счётчик провалов, выполнить dashboard_reset и перезапустить цикл.
           После превышения лимита подряд провалов — уходим в restart_account()."""
        # дебаунс: не допускаем параллельных reset
        if getattr(self, "_reset_in_progress", False):
            print(f"[reset] skip (already in progress), reason={reason}")
            return
        self._reset_in_progress = True

        try:
            # аккуратная проверка лимита, чтобы не было '4/3'
            next_fail = self._fail_streak + 1
            if next_fail >= self._max_resets:
                self._fail_streak = self._max_resets
                print(f"[reset] reason={reason}, streak={self._fail_streak}/{self._max_resets} (limit)")
                print("[reset] max attempts reached → restart_account()")
                self.restart_account()
                return

            # увеличиваем счётчик и продолжаем reset-процедуру
            self._fail_streak = next_fail
            print(f"[reset] reason={reason}, streak={self._fail_streak}/{self._max_resets}")

            # 1) сброс дашборда
            try:
                self._run_dashboard_reset()
            except Exception as e:
                print(f"[reset] dashboard_reset error: {e}")

            # 2) если всё ещё мёртвы — повторная попытка «В деревню»
            try:
                if not self.watcher.is_alive():
                    self._revive_decided = False
                    ui_ok = (
                        getattr(self, "respawn_ui", None)
                        and getattr(self.respawn_ui, "is_enabled", None)
                        and self.respawn_ui.is_enabled()
                    )
                    if ui_ok:
                        print("[reset] still dead → retry ToVillage")
                        threading.Thread(target=self._raise_after_death, daemon=True).start()
            except Exception as e:
                print(f"[reset] revive retry error: {e}")

            # 3) метки и запуск цикла
            self._tp_success = False
            self._buff_was_success = False
            self._flow_interrupted = True

            if not getattr(self, "_awaiting_alive_restart", False):
                self._awaiting_alive_restart = True
                try:
                    self.root.after(0, self._run_alive_flow)
                except Exception:
                    self._run_alive_flow()

        finally:
            self._reset_in_progress = False


    def _run_dashboard_reset(self) -> bool:
        """Выполнить flow core/servers/<server>/flows/dashboard_reset.py
           Зоны/шаблоны берём из zones.tp (там есть dashboard_body, dashboard_init)."""
        try:
            flow_mod = importlib.import_module(f"core.servers.{self.server}.flows.dashboard_reset")
            flow = getattr(flow_mod, "FLOW", [])
        except Exception as e:
            print(f"[reset] load flow error: {e}")
            return False

        try:
            zones_mod = importlib.import_module(f"core.servers.{self.server}.zones.tp")
            zones = getattr(zones_mod, "ZONES", {})
            templates = getattr(zones_mod, "TEMPLATES", {})
        except Exception as e:
            print(f"[reset] zones load error: {e}")
            zones, templates = {}, {}

        ctx = FlowCtx(
            server=self.server,
            controller=self.controller,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            zones=zones,
            templates=templates,
            extras={},
        )
        execu = FlowOpExecutor(ctx, on_status=lambda msg, ok: print(msg), logger=lambda m: print(m))
        ok = run_flow(flow, execu)
        print(f"[reset] dashboard_reset → {ok}")
        return ok

    def restart_account(self):
        print("[reset] restart_account (stub)")
        # сбросить счётчик и флаги, чтобы не было повторных «waiting alive…»
        self._fail_streak = 0
        self._flow_interrupted = False

    def _is_row_selected(self) -> bool:
        get_row = getattr(self.tp, "get_selected_row_id", None)
        return bool(callable(get_row) and get_row())

    def _mark_cycle_success(self, where: str):
        if self._fail_streak:
            print(f"[reset] success at {where} → streak 0")
        self._fail_streak = 0
        self._flow_interrupted = False
        self._cycle_success_marked = True
    # ---------------- respawn controls ----------------
    def _respawn_start(self):
        if not self.watcher.is_running():
            self.watcher.start()
            print("[state] watcher ON")
        else:
            print("[state] watcher already running")

    def _respawn_stop(self):
        if self.watcher.is_running():
            self.watcher.stop()
        print("[state] watcher OFF")

    def _toggle_autobuff(self, enabled: bool):
        self._autobuff_enabled = bool(enabled)
        # поллер уже крутится; флаг управляет логикой в _buff_interval_tick

    # ---------------- helpers ----------------
    def _safe_window(self):
        try:
            return self.winprobe.current_window_info()
        except Exception:
            return None

    def _check_is_dead(self) -> bool:
        try:
            return not self.watcher.is_alive()
        except Exception:
            return False

    # ---------------- UI build ----------------
    def build_ui(self, parent: tk.Widget, local_version: str):
        # Блок 1: системные настройки (язык, сервер, поиск окна, коннект, версия, апдейт, выход)
        top = _Collapsible(parent, "Системные настройки", opened=True)
        top.pack(fill="x", padx=8, pady=4)

        # язык
        lang_frame = tk.Frame(top.body())
        lang_frame.pack(pady=(5, 2), anchor="center")
        tk.Label(lang_frame, text="Язык интерфейса:", font=("Arial", 10)).pack(side="left", padx=(0, 6))
        ttk.OptionMenu(
            lang_frame, self.language_var, self.language_var.get(), "rus", "eng", command=self.set_language
        ).pack(side="left", padx=(0, 20))

        # сервер
        server_frame = tk.Frame(top.body())
        server_frame.pack(pady=(2, 6), anchor="center")
        tk.Label(server_frame, text="Сервер:", font=("Arial", 10)).pack(side="left", padx=(0, 12))
        ttk.OptionMenu(server_frame, self.server_var, self.server_var.get(), "l2mad", command=self.set_server).pack(
            side="left", padx=(0, 20)
        )

        # окно
        window_frame = tk.Frame(top.body())
        window_frame.pack(pady=(2, 10), anchor="center")
        tk.Button(window_frame, text="🔍 Найти окно Lineage", command=self.winprobe.try_find_window_again).pack(
            side="left", padx=(0, 8)
        )
        ws_label = tk.Label(top.body(), text="[?] Поиск окна...", font=("Arial", 9), fg="gray")
        ws_label.pack()
        self.winprobe.attach_status(ws_label)

        # связь
        self.driver_status = tk.Label(top.body(), text="Состояние связи: неизвестно", fg="gray")
        tk.Button(
            top.body(), text="🧪 Тест коннекта", command=lambda: run_test_command(self.controller, self.driver_status)
        ).pack(pady=5)
        self.driver_status.pack(pady=(0, 5))

        # версия + апдейтер
        tk.Label(top.body(), text=f"Версия: {local_version}", font=("Arial", 10)).pack()
        self.version_status_label = tk.Label(top.body(), text="", font=("Arial", 9), fg="orange")
        self.version_status_label.pack()
        tk.Button(
            top.body(),
            text="🔄 Проверить обновление",
            command=lambda: run_update_check(local_version, self.version_status_label, self.root, self),
        ).pack()

        # выход
        tk.Button(top.body(), text="Выход", fg="red", command=self.exit_program).pack(pady=10)

        # Блок 2: рабочий поток — отслеживание состояния · Баф · Макросы · ТП
        flow = _Collapsible(parent, "Отслеживать состояние · Баф · Макросы · ТП", opened=True)
        flow.pack(fill="x", padx=8, pady=4)

        # 1) Мониторинг/подъём
        self.respawn_ui = RespawnControls(parent=flow.body(), start_fn=self._respawn_start, stop_fn=self._respawn_stop)
        StateControls(parent=self.respawn_ui.get_body(), state_getter=lambda: self.watcher.last())

        # 2) Баф
        self.buff = BuffControls(
            parent=flow.body(),
            controller=self.controller,
            server_getter=lambda: self.server,
            language_getter=lambda: self.language,
            get_window=lambda: self._safe_window(),
            profile_getter=lambda: self.profile,
            window_found_getter=lambda: bool(self.winprobe.window_found),
        )
        BuffIntervalControl(
            flow.body(),
            checker=self.checker,
            on_toggle_autobuff=self._toggle_autobuff,
            intervals=(1, 5, 10, 20),
        )

        # 3) Макросы после бафа
        self.afterbuff_ui = AfterBuffMacrosControls(flow.body())
        self.afterbuff_runner = AfterBuffMacroRunner(
            controller=self.controller,
            get_sequence=lambda: self.afterbuff_ui.get_sequence(),
            get_delay_s=lambda: self.afterbuff_ui.get_delay_s(),
        )

        # 4) ТП
        tp_frame = tk.LabelFrame(flow.body(), text="Телепорт", padx=6, pady=6)
        tp_frame.pack(fill="x", padx=6, pady=6, anchor="w")
        self.tp = TPControls(
            parent=tp_frame,
            controller=self.controller,
            get_language=lambda: self.language,
            get_window_info=lambda: self._safe_window(),
            profile_getter=lambda: self.profile,
            check_is_dead=self._check_is_dead,
        )

        # --- блок: маршрут после ТП ---
        rows_frame = tk.Frame(tp_frame)  # ← привязываем к секции ТП
        rows_frame.pack(fill="x", padx=6, pady=(4, 6), anchor="w")

        tk.Label(rows_frame, text="Маршрут после ТП:").pack(side="left", padx=(0, 8))
        self._rows_menu = ttk.Combobox(
            rows_frame,
            textvariable=self._row_var,
            state="readonly",
            width=28,
            values=[],
        )
        self._rows_menu.pack(side="left")
        self._rows_menu.bind("<<ComboboxSelected>>", self._on_row_selected)
        ttk.Button(rows_frame, text="Очистить", command=self._clear_row).pack(side="left", padx=6)

        # автоподгрузка маршрутов при смене пункта ТП
        self.root.after(200, self._rows_watch)

        # авто-проверка обновлений
        def _schedule_update_check():
            run_update_check(local_version, self.version_status_label, self.root, self)
            self.root.after(600_000, _schedule_update_check)

        _schedule_update_check()

    # ---------------- window probe callbacks ----------------
    def _on_window_found(self, win_info: dict):
        br = getattr(self, "buff_runner", None)
        supports = bool(getattr(self.profile, "supports_buffing", lambda: False)())
        if br and supports and not br.is_running():
            br.start()

    # ---------------- setters ----------------
    def set_language(self, lang):
        self.language = (lang or "rus").lower()
        print(f"[UI] Язык интерфейса установлен: {self.language}")
        # watcher берет язык через callback, ничего делать не нужно

    def set_server(self, server):
        self.server = (server or "l2mad").lower()
        print(f"[UI] Сервер установлен: {self.server}")
        self.profile = get_server_profile(self.server)

        br = getattr(self, "buff_runner", None)
        if br and br.is_running():
            br.stop()
        if hasattr(self.profile, "buff_tick"):
            self.buff_runner = RepeaterThread(
                fn=lambda: self.profile.buff_tick(self._safe_window(), self.controller, language=self.language, debug=True),
                interval=15.0,
                debug=False,
            )
        else:
            self.buff_runner = None

        try:
            self.watcher.set_server(self.server)
        except Exception:
            pass
        try:
            self.to_village.set_server(self.server)
        except Exception:
            pass
        try:
            self.buff.refresh_enabled(self.profile)
        except Exception:
            pass

    # ---------------- rows (post-TP) ----------------
    def _rows_watch(self):
        get_sel = getattr(self.tp, "get_selected_destination", None)
        dest = get_sel() if callable(get_sel) else ("", "")
        # print("[rows] dest:", dest)  # ← увидеть ("cat_id","loc_id")
        if dest != self._last_row_dest:
            self._last_row_dest = dest
            self._reload_rows()
        try:
            self.root.after(400, self._rows_watch)
        except Exception:
            pass

    def _row_id_from_title(self, title: str):
        for rid, t in self._rows_cache:
            if t == title:
                return rid
        return None

    def _on_row_selected(self, *_):
        rid = self._row_id_from_title(self._row_var.get() or "")
        try:
            self.tp.set_selected_row_id(rid or "")
        except Exception:
            pass

    def _reload_rows(self):
        cat, loc = self._last_row_dest
        try:
            rows = list_rows(cat, loc) if (cat and loc) else []
        except Exception:
            rows = []

        lang = (self.language or "rus").lower()

        def title_of(r):
            if lang == "rus":
                return r.get("title_rus") or r.get("id")
            return r.get("title_eng") or r.get("title_rus") or r.get("id")

        self._rows_cache = [(r["id"], title_of(r)) for r in rows if r.get("id")]
        values_list = [t for (_id, t) in self._rows_cache]

        if self._rows_menu:
            try:
                self._rows_menu["values"] = values_list
            except Exception:
                pass

        cur_id = self._row_id_from_title(self._row_var.get() or "")
        valid_ids = [rid for (rid, _t) in self._rows_cache]

        if not values_list:
            self._row_var.set("")
            self._on_row_selected()
        elif cur_id not in valid_ids:
            self._row_var.set(values_list[0])
            self._on_row_selected()


    def _clear_row(self):
        self._row_var.set("")
        self._on_row_selected()

    # ---------------- shutdown ----------------
    def exit_program(self):
        try:
            self.respawn.stop()
        except Exception:
            pass
        try:
            if self.buff_runner:
                self.buff_runner.stop()
        except Exception:
            pass
        try:
            self.watcher.stop()
        except Exception:
            pass
        if self.controller:
            try:
                self.controller.close()
            except Exception:
                pass
        try:
            if self.charge_poller:
                self.charge_poller.stop()
        except Exception:
            pass
        self.root.destroy()
        sys.exit(0)


# ---------------- entry ----------------
def launch_gui(local_version: str):
    root = tk.Tk()
    root.title("Revive Launcher")
    root.geometry("620x1180")
    root.resizable(False, False)

    tk.Label(root, text="Revive", font=("Arial", 20, "bold"), fg="orange").pack(pady=10)
    tk.Label(root, text="Функции:", font=("Arial", 12, "bold")).pack(pady=(5))

    parent = tk.Frame(root)
    parent.pack(pady=10, fill="both")

    app = ReviveLauncherUI(root)
    app.build_ui(parent, local_version)

    root.protocol("WM_DELETE_WINDOW", app.exit_program)
    logging.info("[launcher] loaded")
    root.mainloop()
