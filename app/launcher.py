# app/launcher.py
from __future__ import annotations
import sys
import tkinter as tk
import tkinter.ttk as ttk
import logging

from core.connection import ReviveController
from core.connection_test import run_test_command
from core.features.auto_respawn_runner import AutoRespawnRunner
from core.features.auto_revive_on_zero_hp import AutoReviveOnZeroHP
from core.servers.registry import get_server_profile
from core.runtime.poller import RepeaterThread

from app.ui.window_probe import WindowProbe
from app.ui.state_controls import StateControls
from app.ui.respawn_controls import RespawnControls
from app.ui.buff_controls import BuffControls
from app.ui.tp_controls import TPControls
from app.ui.updater_dialog import run_update_check

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

        # --- controller ---
        self.controller = ReviveController()

        # --- server profile FIRST ---
        self.profile = get_server_profile(self.server)

        # --- periodic buff tick placeholder BEFORE any callbacks can fire ---
        self.buff_runner = None
        if hasattr(self.profile, "buff_tick"):
            self.buff_runner = RepeaterThread(
                fn=lambda: self.profile.buff_tick(self._safe_window(), self.controller, language=self.language, debug=True),
                interval=15.0,
                debug=False,
            )

        # --- window probe (автопоиск окна L2). on_found может сработать в __init__, поэтому всё выше уже готово ---
        self.winprobe = WindowProbe(root=self.root, on_found=self._on_window_found)

        # --- auto respawn runner (старый сценарий по шаблонам, может пригодиться отдельно) ---
        self.respawn = AutoRespawnRunner(
            controller=self.controller,
            window_title="Lineage",
            language=self.language,
            server=self.server,
            poll_interval=0.5,
            debug=True,
            window_provider=lambda: self._safe_window(),
        )

        # --- auto revive on HP==0 ---
        self.auto_revive = AutoReviveOnZeroHP(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            poll_interval=0.2,
            zero_hp_threshold=0.01,
            confirm_timeout_s=6.0,
            click_threshold=0.87,
            debug=True,
        )
        self.auto_revive.start()

        # --- ui parts ---
        self.driver_status = None
        self.version_status_label = None

        # ping arduino
        try:
            self.controller.send("ping")
            response = self.controller.read()
            print("[✓] Arduino ответила" if response == "pong" else "[×] Нет ответа")
        except Exception as e:
            print(f"[×] Ошибка связи с Arduino: {e}")

        self.update_window_ref = None

    # ---------------- respawn controls ----------------
    def _respawn_start(self):
        # запускает AutoReviveOnZeroHP, в котором уже внутри стартует PlayerStateMonitor
        self.auto_revive.start()
        print("[respawn] auto revive + state monitor ON")

    def _respawn_stop(self):
        self.auto_revive.stop()
        print("[respawn] auto revive + state monitor OFF")

    # ---------------- helpers ----------------
    def _safe_window(self):
        try:
            return self.winprobe.current_window_info()
        except Exception:
            return None

    # ---------------- UI build ----------------
    def build_ui(self, parent: tk.Widget, local_version: str):
        version_frame = tk.Frame(parent); version_frame.pack(padx=10, pady=10, fill="x")

        # language selector
        lang_frame = tk.Frame(parent); lang_frame.pack(pady=(5, 2))
        tk.Label(lang_frame, text="Язык интерфейса:", font=("Arial", 10)).pack(side="left", padx=(0, 6))
        ttk.OptionMenu(lang_frame, self.language_var, self.language_var.get(), "rus", "eng", command=self.set_language).pack(side="left")

        # server selector
        server_frame = tk.Frame(parent); server_frame.pack(pady=(2, 6))
        tk.Label(server_frame, text="Сервер:", font=("Arial", 10)).pack(side="left", padx=(0, 34))
        ttk.OptionMenu(server_frame, self.server_var, self.server_var.get(), "l2mad", command=self.set_server).pack(side="left")

        # window probe controls
        window_frame = tk.Frame(parent); window_frame.pack(pady=(2, 10))
        tk.Button(window_frame, text="🔍 Найти окно Lineage", command=self.winprobe.try_find_window_again).pack(side="left", padx=(0, 8))
        ws_label = tk.Label(window_frame, text="[?] Поиск окна...", font=("Arial", 9), fg="gray"); ws_label.pack(side="left")
        self.winprobe.attach_status(ws_label)

        # connection test
        self.driver_status = tk.Label(parent, text="Состояние связи: неизвестно", fg="gray")
        tk.Button(parent, text="🧪 Тест коннекта", command=lambda: run_test_command(self.controller, self.driver_status)).pack(pady=5)
        self.driver_status.pack(pady=(0, 5))

        # version + updater
        tk.Label(parent, text=f"Версия: {local_version}", font=("Arial", 10)).pack()
        self.version_status_label = tk.Label(parent, text="", font=("Arial", 9), fg="orange"); self.version_status_label.pack()
        tk.Button(parent, text="🔄 Проверить обновление",
                  command=lambda: run_update_check(local_version, self.version_status_label, self.root, self)).pack()

        # exit button
        tk.Button(parent, text="Выход", fg="red", command=self.exit_program).pack(side="bottom", pady=10)

        # 1) Автовозрождение (UI)
        RespawnControls(
            parent=parent,
            start_fn=self._respawn_start,
            stop_fn=self._respawn_stop,
        )

        # 2) Баф после респавна (UI)
        self.buff = BuffControls(
            parent=parent,
            controller=self.controller,
            server_getter=lambda: self.server,
            language_getter=lambda: self.language,
            get_window=lambda: self._safe_window(),
            profile_getter=lambda: self.profile,
            window_found_getter=lambda: bool(self.winprobe.window_found),
        )

        # 3) ТП (UI)
        self.tp = TPControls(
            parent=parent,
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
        # Защита: buff_runner мог не быть создан, если профиль не поддерживает
        br = getattr(self, "buff_runner", None)
        supports = bool(getattr(self.profile, "supports_buffing", lambda: False)())
        if br and supports and not br.is_running():
            br.start()

    # ---------------- state monitor (HP) ----------------
    def _state_start(self):
        try:
            self.auto_revive.start()
            print("[state] monitor ON")
        except Exception as e:
            print(f"[state] start error: {e}")

    def _state_stop(self):
        try:
            self.auto_revive.stop()
            print("[state] monitor OFF")
        except Exception as e:
            print(f"[state] stop error: {e}")

    def _check_is_dead(self) -> bool:
        try:
            return bool(self.auto_revive._state.hp_ratio <= 0.01)
        except Exception:
            return False

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

        # обновить buff runner доступность
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

        # обновить auto_revive сервер
        self.auto_revive.set_server(self.server)

        # уведомить BuffControls о новом профиле/сервере
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
            self.auto_revive.stop()
        except Exception:
            pass
        if self.controller:
            try:
                self.controller.close()
            except Exception:
                pass
        self.root.destroy()
        sys.exit(0)


# ---------------- entry ----------------
def launch_gui(local_version: str):
    root = tk.Tk()
    root.title("Revive Launcher")
    root.geometry("420x720")
    root.resizable(False, False)

    tk.Label(root, text="Revive", font=("Arial", 20, "bold"), fg="orange").pack(pady=10)
    tk.Label(root, text="Функции:", font=("Arial", 12, "bold")).pack(pady=(5))

    parent = tk.Frame(root); parent.pack(pady=10, fill="both")

    app = ReviveLauncherUI(root)
    app.build_ui(parent, local_version)

    root.protocol("WM_DELETE_WINDOW", app.exit_program)
    logging.info("[launcher] loaded")
    root.mainloop()
