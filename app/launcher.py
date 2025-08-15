# app/launcher.py
from __future__ import annotations
import traceback
import sys
import threading
import tkinter as tk
import tkinter.ttk as ttk
import logging
import time  # ← вот это


from core.connection import ReviveController
from core.connection_test import run_test_command
from core.servers.registry import get_server_profile

from core.runtime.state_watcher import StateWatcher
from core.runtime.poller import RepeaterThread

# from core.features.auto_respawn_runner import AutoRespawnRunner
from core.features.to_village import ToVillage
from core.features.afterbuff_macros import AfterBuffMacroRunner

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

        # --- window probe ---
        self.winprobe = WindowProbe(root=self.root, on_found=self._on_window_found)

        # --- auto respawn runner (старый, отдельно) ---
        # self.respawn = AutoRespawnRunner(
        #     controller=self.controller,
        #     window_title="Lineage",
        #     language=self.language,
        #     server=self.server,
        #     poll_interval=0.5,
        #     debug=True,
        #     window_provider=lambda: self._safe_window(),
        # )

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
            },
            order=PRIORITY,
        )

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
            return

        if self._charged_flag is not True:
            print(f"[flow] tp_if_ready → skip (not charged: {self._charged_flag})")
            return

        fn = getattr(self.tp, "teleport_now_selected", None)
        ok_tp = bool(fn()) if callable(fn) else False
        print(f"[flow] tp_if_ready → {ok_tp}")
        # одноразово на цикл «умер→встал»
        self._tp_after_death = False

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
            self._tp_after_death = bool(ok)   # True только если реально нажали и поднялись
        except Exception as e:
            print(f"[to_village] error in thread: {e}")
            self._tp_after_death = False
        finally:
            self._revive_decided = True       # решение принято в любом случае

    def _on_dead_ui(self, st):
        self._alive_flag = False
        self._charged_flag = None
        print("[state] death detected → charged=None")
        try:
            self.checker.invalidate()          # ← ВАЖНО: сбросить кеш при смерти
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
        # если в UI включено «встать после смерти» — ждём решения, кто поднял
        try:
            ui_wants_raise = getattr(self, "respawn_ui", None) and self.respawn_ui.is_enabled()
        except Exception:
            ui_wants_raise = False

        if ui_wants_raise and not getattr(self, "_revive_decided", True):
            # небольшая задержка и пробуем снова
            try: self.root.after(300, self._run_alive_flow)
            except Exception: time.sleep(0.3); self._run_alive_flow()
            return

        self._buff_was_success = False   # ← ДОБАВЬ сбросить результат бафа текущего цикла?
        self.flow.run()

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
        lang_frame = tk.Frame(top.body()); lang_frame.pack(pady=(5, 2), anchor="center")
        tk.Label(lang_frame, text="Язык интерфейса:", font=("Arial", 10)).pack(side="left", padx=(0, 6))
        ttk.OptionMenu(lang_frame, self.language_var, self.language_var.get(), "rus", "eng", command=self.set_language).pack(side="left", padx=(0, 20))

        # сервер
        server_frame = tk.Frame(top.body()); server_frame.pack(pady=(2, 6), anchor="center")
        tk.Label(server_frame, text="Сервер:", font=("Arial", 10)).pack(side="left", padx=(0, 12))
        ttk.OptionMenu(server_frame, self.server_var, self.server_var.get(), "l2mad", command=self.set_server).pack(side="left", padx=(0, 20))

        # окно
        window_frame = tk.Frame(top.body()); window_frame.pack(pady=(2, 10), anchor="center")
        tk.Button(window_frame, text="🔍 Найти окно Lineage", command=self.winprobe.try_find_window_again).pack(side="left", padx=(0, 8))
        ws_label = tk.Label(window_frame, text="[?] Поиск окна...", font=("Arial", 9), fg="gray"); ws_label.pack(side="left")
        self.winprobe.attach_status(ws_label)

        # связь
        self.driver_status = tk.Label(top.body(), text="Состояние связи: неизвестно", fg="gray")
        tk.Button(top.body(), text="🧪 Тест коннекта", command=lambda: run_test_command(self.controller, self.driver_status)).pack(pady=5)
        self.driver_status.pack(pady=(0, 5))

        # версия + апдейтер
        tk.Label(top.body(), text=f"Версия: {local_version}", font=("Arial", 10)).pack()
        self.version_status_label = tk.Label(top.body(), text="", font=("Arial", 9), fg="orange"); self.version_status_label.pack()
        tk.Button(top.body(), text="🔄 Проверить обновление",
                  command=lambda: run_update_check(local_version, self.version_status_label, self.root, self)).pack()

        # выход
        tk.Button(top.body(), text="Выход", fg="red", command=self.exit_program).pack(pady=10)

        # Блок 2: рабочий поток — отслеживание состояния · баф · макросы · ТП
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
        from app.ui.afterbuff_macros import AfterBuffMacrosControls
        from core.features.afterbuff_macros import AfterBuffMacroRunner
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
        self.respawn.set_language(self.language)

    def set_server(self, server):
        self.server = (server or "l2mad").lower()
        print(f"[UI] Сервер установлен: {self.server}")
        self.respawn.set_server(self.server)
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

    parent = tk.Frame(root); parent.pack(pady=10, fill="both")

    app = ReviveLauncherUI(root)
    app.build_ui(parent, local_version)

    root.protocol("WM_DELETE_WINDOW", app.exit_program)
    logging.info("[launcher] loaded")
    root.mainloop()
