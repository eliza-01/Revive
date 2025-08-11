import sys
import tkinter as tk
import tkinter.ttk as ttk
import logging

from core.logging_setup import init_logging
from core.connection import ReviveController
from core.connection_test import run_test_command
from core.features.auto_respawn_runner import AutoRespawnRunner
from core.features.auto_revive_on_zero_hp import AutoReviveOnZeroHP
from core.features.player_state import PlayerState, PlayerStateMonitor
from core.servers.registry import get_server_profile, list_servers
from core.runtime.poller import RepeaterThread

from app.ui.state_controls import StateControls
from app.ui.updater_dialog import run_update_check
from app.ui.window_probe import WindowProbe
from app.ui.buff_controls import BuffControls
from app.ui.tp_controls import TPControls

LOG_PATH = init_logging()

def _status_sink(text, ok=None):
    print(text)

class ReviveLauncherUI:
    def __init__(self, root):
        self.root = root
        self.running = False
        self.language = "rus"
        self.language_var = tk.StringVar(value=self.language)
        self.server = "l2mad"
        self.server_var = tk.StringVar(value=self.server)

        self.controller = ReviveController()
        self.profile = get_server_profile(self.server)
        self.buff_runner = None

        self.winprobe = WindowProbe(root=self.root, on_found=self._on_window_found)

        self.respawn = AutoRespawnRunner(
            controller=self.controller,
            window_title="Lineage",
            language=self.language,
            server=self.server,
            poll_interval=0.5,
            debug=True,
            window_provider=lambda: self.winprobe.current_window_info(),
        )

        if hasattr(self.profile, "buff_tick"):
            self.buff_runner = RepeaterThread(
                fn=lambda: self.profile.buff_tick(self.winprobe.current_window_info(), self.controller, language=self.language, debug=True),
                interval=15.0,
                debug=False,
            )

        # Автоподъём при 0% HP
        self.auto_revive = AutoReviveOnZeroHP(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self.winprobe.current_window_info(),
            get_language=lambda: self.language,
            poll_interval=0.2,
            zero_hp_threshold=0.01,
            confirm_timeout_s=6.0,
            click_threshold=0.87,
            debug=True,
        )
        self.auto_revive.start()

        self.driver_status = None
        self.version_status_label = None
        self.auto_respawn_var = None

        self.buff = BuffControls(
            parent=root,
            profile_getter=lambda: self.profile,
            language_getter=lambda: self.language,
            window_found_getter=lambda: bool(self.winprobe.window_found),
        )
        self.tp = None

        try:
            self.controller.send("ping")
            response = self.controller.read()
            print("[✓] Arduino ответила" if response == "pong" else "[×] Нет ответа")
        except Exception as e:
            print(f"[×] Ошибка связи с Arduino: {e}")

        self.update_window_ref = None

        # Монитор состояния персонажа (HP)
        self.state_monitor = PlayerStateMonitor(
            server=self.server,
            get_window=lambda: self.winprobe.current_window_info(),
            on_update=lambda st: None,  # можно вывести в статус-бар при желании
            poll_interval=0.2,
            debug=False,
        )

        self.driver_status = None
        self.version_status_label = None
        self.auto_respawn_var = None

        self.buff = BuffControls(
            parent=root,
            profile_getter=lambda: self.profile,
            language_getter=lambda: self.language,
            window_found_getter=lambda: bool(self.winprobe.window_found),
        )
        self.tp = None

        try:
            self.controller.send("ping")
            response = self.controller.read()
            print("[✓] Arduino ответила" if response == "pong" else "[×] Нет ответа")
        except Exception as e:
            print(f"[×] Ошибка связи с Arduino: {e}")

        self.update_window_ref = None

    def build_ui(self, parent: tk.Widget, local_version: str):
        window_frame = tk.Frame(parent); window_frame.pack(pady=(2, 10))
        tk.Button(window_frame, text="🔍 Найти окно Lineage", command=self.winprobe.try_find_window_again).pack(side="left", padx=(0, 8))
        window_status_label = tk.Label(window_frame, text="[?] Поиск окна...", font=("Arial", 9), fg="gray"); window_status_label.pack(side="left")
        self.winprobe.attach_status_label(window_status_label)

        lang_frame = tk.Frame(parent); lang_frame.pack(pady=(5, 2))
        tk.Label(lang_frame, text="Язык интерфейса:", font=("Arial", 10)).pack(side="left", padx=(0, 6))
        ttk.OptionMenu(lang_frame, self.language_var, self.language_var.get(), "rus", "eng", command=self.set_language).pack(side="left")

        server_frame = tk.Frame(parent); server_frame.pack(pady=(2, 6))
        tk.Label(server_frame, text="Сервер:", font=("Arial", 10)).pack(side="left", padx=(0, 34))
        servers = list_servers()
        ttk.OptionMenu(server_frame, self.server_var, self.server_var.get(), *servers, command=self.set_server).pack(side="left")

        self.driver_status = tk.Label(parent, text="Состояние связи: неизвестно", fg="gray")
        tk.Button(parent, text="🧪 Тест коннекта", command=lambda: run_test_command(self.controller, self.driver_status)).pack(pady=5)
        self.driver_status.pack(pady=(0, 5))

        version_frame = tk.Frame(parent); version_frame.pack(padx=10, pady=10, fill="x")
        tk.Label(version_frame, text=f"Версия: {local_version}", font=("Arial", 10)).pack()
        self.version_status_label = tk.Label(version_frame, text="", font=("Arial", 9), fg="orange"); self.version_status_label.pack()
        tk.Button(version_frame, text="🔄 Проверить обновление", command=lambda: run_update_check(local_version, self.version_status_label, self.root, self)).pack()

        self.tp = TPControls(
            parent=version_frame,
            controller=self.controller,
            get_language=lambda: self.language,
            get_window_info=lambda: self.winprobe.current_window_info(),
            profile_getter=lambda: self.profile,
            check_is_dead=self._check_is_dead,
        )
        self.tp.pack(anchor="w", fill="x")

        # Чекбокс автоподъёма
        self.auto_respawn_var = tk.BooleanVar()
        tk.Checkbutton(parent, text="Встать после смерти 💀", font=("Arial", 14, "bold"), variable=self.auto_respawn_var, command=lambda: self.on_toggle_auto_respawn(self.auto_respawn_var.get())).pack(pady=3)

        # Блок бафа
        self.buff.frame.master = parent

        # Блок отслеживания состояния (HP). По умолчанию включено.
        StateControls(
            parent=parent,
            start_fn=self._state_start,
            stop_fn=self._state_stop,
        )

        tk.Button(parent, text="Выход", fg="red", command=self.exit_program).pack(side="bottom", pady=10)

    # ------- handlers -------
    def _state_start(self):
        self.state_monitor.set_server(self.server)
        self.state_monitor.start()

    def _state_stop(self):
        self.state_monitor.stop()

    def set_language(self, lang):
        self.language = (lang or "rus").lower()
        print(f"[UI] Язык интерфейса установлен: {self.language}")
        self.respawn.set_language(self.language)

    def set_server(self, server):
        self.server = (server or "l2mad").lower()
        print(f"[UI] Сервер установлен: {self.server}")
        self.respawn.set_server(self.server)
        self.profile = get_server_profile(self.server)
        self.buff.refresh_enabled(self.profile)

        if hasattr(self.profile, "buff_tick"):
            if self.buff_runner and self.buff_runner.is_running():
                self.buff_runner.stop()
            self.buff_runner = RepeaterThread(
                fn=lambda: self.profile.buff_tick(self.winprobe.current_window_info(), self.controller, language=self.language, debug=True),
                interval=15.0,
                debug=False,
            )
        else:
            self.buff_runner = None

        # обновляем и авто-подъём по 0% HP
        self.auto_revive.set_server(self.server)

    def on_toggle_auto_respawn(self, is_enabled):
        if is_enabled:
            if not self.winprobe.window_found:
                print("[UI] Сначала дождись, пока будет найдено окно (или нажми «Найти окно»).")
                return
            if not self.respawn.is_running():
                self.respawn.set_post_respawn_hook(lambda win: self._post_respawn_actions(win))
                self.respawn.start()
            print("[UI] Автовставание ВКЛ")
            self.running = True
            self.buff.pack()
        else:
            print("[UI] Автовставание ВЫКЛ")
            self.running = False
            self.respawn.stop()
            self.buff.pack_forget()
            self.buff.enabled_var.set(False)

    def _post_respawn_actions(self, window_info: dict):
        # 1) Баф после респавна
        if self.buff.is_enabled() and getattr(self.profile, "supports_buffing", lambda: False)():
            try:
                buff_worker = BuffAfterRespawnWorker(
                    controller=self.controller,
                    server=self.server,
                    get_window=lambda: self.winprobe.current_window_info(),
                    get_language=lambda: self.language,
                    on_status=_status_sink,
                )
                buff_worker.set_mode(self.buff.get_mode())
                buff_worker.set_method(self.buff.get_method())
                ok_buff = buff_worker.run_once()
                print(f"[buff] {'ok' if ok_buff else 'fail'}")
            except Exception as e:
                print(f"[buff] Ошибка: {e}")
        else:
            print("[buff] Пропуск")

        # 2) ТП после респавна
        try:
            if self.tp.is_enabled():
                worker = self.tp._ensure_worker()
                worker.window = window_info
                cat, loc, method = self.tp.selection()
                print(f"[tp] Попытка ТП → {method} :: {cat} / {loc}")
                ok_tp = self.tp.teleport_now_selected()
                print(f"[tp] {'Успешно' if ok_tp else 'Не удалось'}: {cat} → {loc}")
            else:
                print("[tp] Пропуск: ТП выключено или не выбрана категория/локация")
        except Exception as e:
            print(f"[tp] Ошибка ТП после респавна: {e}")

    def _on_window_found(self, _info: dict):
        br = getattr(self, "buff_runner", None)
        if br and self.buff.is_enabled() and not br.is_running():
            br.start()

    def _check_is_dead(self) -> bool:
        try:
            if hasattr(self.respawn, "is_dead"):
                return bool(self.respawn.is_dead())
            return False
        except Exception:
            return False

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

def launch_gui(local_version: str):
    root = tk.Tk()
    root.title("Revive Launcher")
    root.geometry("420x700")
    root.resizable(False, False)
    tk.Label(root, text="Revive", font=("Arial", 20, "bold"), fg="orange").pack(pady=10)
    tk.Label(root, text="Функции:", font=("Arial", 12, "bold")).pack(pady=(5))
    parent = tk.Frame(root); parent.pack(pady=10)
    app = ReviveLauncherUI(root)
    app.build_ui(parent, local_version)
    root.protocol("WM_DELETE_WINDOW", app.exit_program)
    logging.info("[launcher] loaded")
    def schedule_update_check():
        run_update_check(local_version, app.version_status_label, root, app)
        root.after(600_000, schedule_update_check)
    schedule_update_check()
    root.mainloop()
