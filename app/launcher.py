# app/launcher.py
import sys
import tkinter as tk
import tkinter.ttk as ttk
import logging

from core.logging_setup import init_logging
from core.connection import ReviveController
from core.connection_test import run_test_command
from core.features.auto_respawn_runner import AutoRespawnRunner
from core.servers.registry import get_server_profile
from core.runtime.poller import RepeaterThread
from core.vision.capture import gdi

from app.ui.updater_dialog import run_update_check
from app.ui.window_probe import WindowProbe
from app.ui.buff_controls import BuffControls
from app.ui.tp_controls import TPControls

# инициализация логирования и прокси print
LOG_PATH = init_logging()

class ReviveLauncherUI:
    def __init__(self, root):
        self.root = root

        # состояние
        self.running = False
        self.language = "rus"
        self.language_var = tk.StringVar(value=self.language)
        self.server = "l2mad"
        self.server_var = tk.StringVar(value=self.server)

        # контроллер
        self.controller = ReviveController()

        # профиль сервера
        self.profile = get_server_profile(self.server)

        # окно Lineage
        self.winprobe = WindowProbe(root=self.root, on_found=self._on_window_found)

        # авто-респавн
        self.respawn = AutoRespawnRunner(
            controller=self.controller,
            window_title="Lineage",
            language=self.language,
            server=self.server,
            poll_interval=3.0,
            debug=True,
        )

        # опциональный периодический тик бафа
        if hasattr(self.profile, "buff_tick"):
            self.buff_runner = RepeaterThread(
                fn=lambda: self.profile.buff_tick(self.winprobe.current_window_info(), self.controller, language=self.language, debug=True),
                interval=15.0,
                debug=False,
            )
        else:
            self.buff_runner = None

        # UI references
        self.driver_status = None
        self.version_status_label = None
        self.auto_respawn_var = None

        # дочерние блоки UI
        self.buff = BuffControls(
            parent=root,  # временно, настоящий parent задаётся в build_ui
            profile_getter=lambda: self.profile,
            language_getter=lambda: self.language,
            window_found_getter=lambda: bool(self.winprobe.window_found),
        )
        self.tp = None  # создадим в build_ui внутри секции версии

        # проверка связи с Arduino
        try:
            self.controller.send("ping")
            response = self.controller.read()
            print("[✓] Arduino ответила" if response == "pong" else "[×] Нет ответа")
        except Exception as e:
            print(f"[×] Ошибка связи с Arduino: {e}")

        # окно обновления, если открыто
        self.update_window_ref = None

    # ---------- UI ----------
    def build_ui(self, parent: tk.Widget, local_version: str):
        # блок статуса окна клиента
        window_frame = tk.Frame(parent)
        window_frame.pack(pady=(2, 10))
        tk.Button(window_frame, text="🔍 Найти окно Lineage", command=self.winprobe.try_find_window_again).pack(side="left", padx=(0, 8))
        window_status_label = tk.Label(window_frame, text="[?] Поиск окна...", font=("Arial", 9), fg="gray")
        window_status_label.pack(side="left")
        self.winprobe.attach_status_label(window_status_label)

        # язык
        lang_frame = tk.Frame(parent)
        lang_frame.pack(pady=(5, 2))
        tk.Label(lang_frame, text="Язык интерфейса:", font=("Arial", 10)).pack(side="left", padx=(0, 6))
        ttk.OptionMenu(
            lang_frame, self.language_var, self.language_var.get(), "rus", "eng", command=self.set_language
        ).pack(side="left")

        # сервер
        server_frame = tk.Frame(parent)
        server_frame.pack(pady=(2, 6))
        tk.Label(server_frame, text="Сервер:", font=("Arial", 10)).pack(side="left", padx=(0, 34))
        ttk.OptionMenu(
            server_frame, self.server_var, self.server_var.get(), "l2mad", command=self.set_server
        ).pack(side="left")

        # коннект/драйвер
        self.driver_status = tk.Label(parent, text="Состояние связи: неизвестно", fg="gray")
        tk.Button(parent, text="🧪 Тест коннекта", command=lambda: run_test_command(self.controller, self.driver_status)).pack(pady=5)
        self.driver_status.pack(pady=(0, 5))

        # версия и обновления
        version_frame = tk.Frame(parent)
        version_frame.pack(padx=10, pady=10, fill="x")
        version_label = tk.Label(version_frame, text=f"Версия: {local_version}", font=("Arial", 10))
        version_label.pack()
        self.version_status_label = tk.Label(version_frame, text="", font=("Arial", 9), fg="orange")
        self.version_status_label.pack()
        tk.Button(version_frame, text="🔄 Проверить обновление", command=lambda: run_update_check(local_version, self.version_status_label, self.root, self)).pack()

        # TPControls живёт рядом с версией
        self.tp = TPControls(
            parent=version_frame,
            controller=self.controller,
            get_language=lambda: self.language,
            get_window_info=lambda: self.winprobe.current_window_info(),
            check_is_dead=self._check_is_dead,
        )
        self.tp.pack(anchor="w", fill="x")

        # автоподъём
        self.auto_respawn_var = tk.BooleanVar()
        tk.Checkbutton(
            parent,
            text="Встать после смерти 💀",
            font=("Arial", 14, "bold"),
            variable=self.auto_respawn_var,
            command=lambda: self.on_toggle_auto_respawn(self.auto_respawn_var.get()),
        ).pack(pady=3)

        # блок бафа (вписываем в parent ниже чекбокса)
        self.buff.frame.master = parent  # переназначаем фактический контейнер
        # по умолчанию скрыт, покажем когда включат автоподъём

        # выход
        tk.Button(parent, text="Выход", fg="red", command=self.exit_program).pack(side="bottom", pady=10)

    # ---------- callbacks ----------
    def set_language(self, lang):
        self.language = (lang or "rus").lower()
        print(f"[UI] Язык интерфейса установлен: {self.language}")
        self.respawn.set_language(self.language)

    def set_server(self, server):
        self.server = (server or "l2mad").lower()
        print(f"[UI] Сервер установлен: {self.server}")
        self.respawn.set_server(self.server)
        # новый профиль
        self.profile = get_server_profile(self.server)
        # обновляем доступность бафа
        self.buff.refresh_enabled(self.profile)

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
            # если был создан buff_runner и окно найдено и баф включат — он стартует по автопоиску
        else:
            print("[UI] Автовставание ВЫКЛ")
            self.running = False
            self.respawn.stop()
            self.buff.pack_forget()
            self.buff.enabled_var.set(False)

    def _post_respawn_actions(self, window_info: dict):
        # 1) Баф
        if self.buff.is_enabled() and getattr(self.profile, "supports_buffing", lambda: False)():
            try:
                mode = self.buff.get_mode()
                print(f"[buff] Запуск сценария бафа: mode={mode} lang={self.language}")
                ok = self.profile.apply_post_respawn_buff(
                    window_info,
                    self.controller,
                    mode=mode,
                    language=self.language,
                    debug=False,
                )
                if not ok:
                    print("[buff] Сценарий бафа не завершился успешно")
            except Exception as e:
                print(f"[buff] Ошибка post-respawn: {e}")
        else:
            print("[buff] Пропуск: автобаф выключен или не поддерживается")

        # 2) ТП
        try:
            if self.tp.is_enabled():
                # актуализируем окно
                worker = self.tp._ensure_worker()
                worker.window = window_info
                cat, loc = self.tp.selection()
                print(f"[tp] Попытка ТП → {cat} / {loc}")
                ok_tp = self.tp.teleport_now_selected()
                if ok_tp:
                    print(f"[tp] Успешно: {cat} → {loc}")
                else:
                    print(f"[tp] Не удалось ТП: {cat} → {loc}")
            else:
                print("[tp] Пропуск: ТП выключено или не выбрана категория/локация")
        except Exception as e:
            print(f"[tp] Ошибка ТП после респавна: {e}")

    def _on_window_found(self, _info: dict):
        # автостарт периодического бафа, если он есть и если пользователь включит чекбокс
        if self.buff_runner and self.buff.is_enabled():
            if not self.buff_runner.is_running():
                self.buff_runner.start()

    # ==== Death detection adapter for TP worker ====
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
    root.geometry("400x560")
    root.resizable(False, False)

    tk.Label(root, text="Revive", font=("Arial", 20, "bold"), fg="orange").pack(pady=10)
    tk.Label(root, text="Функции:", font=("Arial", 12, "bold")).pack(pady=(5))

    parent = tk.Frame(root)
    parent.pack(pady=10)

    app = ReviveLauncherUI(root)
    app.build_ui(parent, local_version)

    root.protocol("WM_DELETE_WINDOW", app.exit_program)
    logging.info("[launcher] loaded")

    # фоновая автопроверка обновлений
    def schedule_update_check():
        run_update_check(local_version, app.version_status_label, root, app)
        root.after(600_000, schedule_update_check)

    schedule_update_check()
    root.mainloop()
