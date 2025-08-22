# app/launcher.py
from __future__ import annotations
import sys
import tkinter as tk
import tkinter.ttk as ttk
import logging

from core.connection import ReviveController
from core.connection_test import run_test_command

from core.servers.registry import get_server_profile, list_servers
from core.runtime.state_watcher import StateWatcher
from core.checks.charged import ChargeChecker, BuffTemplateProbe

from app.ui.window_probe import WindowProbe
from app.ui.state_controls import StateControls
from app.ui.respawn_controls import RespawnControls
from app.ui.buff_controls import BuffControls
from app.ui.tp_controls import TPControls
from app.ui.updater_dialog import run_update_check
# from app.ui.interval_buff import BuffIntervalControl
from app.ui.afterbuff_macros import AfterBuffMacrosControls
from app.ui.account_settings import AccountSettingsDialog
from app.ui.widgets import Collapsible, VScrollFrame

from core.features.afterbuff_macros import AfterBuffMacroRunner
from core.features.post_tp_row import PostTPRowRunner
from core.features.to_village import ToVillage
from core.features.flow_orchestrator import FlowOrchestrator
from core.features.restart_manager import RestartManager
from core.features.autobuff_service import AutobuffService

from app.controllers.rows_controller import RowsController


def _init_logging():
    LOG_PATH = "revive.log"
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(message)s")
    return LOG_PATH


_init_logging()


class ReviveLauncherUI:
    def __init__(self, root: tk.Tk):
        self.root = root

        # --- servers ---
        servers = list_servers() or ["l2mad"]
        self.server = servers[0]
        self.server_var = tk.StringVar(value=self.server)

        # --- state ---
        self.language = "rus"
        self.language_var = tk.StringVar(value=self.language)

        self._charged_flag = None  # отображение, актуальное значение держит orchestrator/checker

        # --- controller ---
        self.controller = ReviveController()

        # --- server profile FIRST ---
        self.profile = get_server_profile(self.server)

        # --- window probe ---
        self.winprobe = WindowProbe(root=self.root, on_found=self._on_window_found)

        # --- watcher: только мониторинг состояния ---
        self.watcher = StateWatcher(
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            poll_interval=0.2,
            zero_hp_threshold=0.01,
            on_state=lambda st: None,
            on_dead=self._on_dead_proxy,
            on_alive=self._on_alive_proxy,
            debug=True,
        )

        # --- checker + probes ---
        self.checker = ChargeChecker(interval_minutes=10, mode="ANY")
        self.checker.register_probe(
            "autobuff_icons",
            BuffTemplateProbe(
                name="autobuff_icons",
                server_getter=lambda: self.server,
                get_window=lambda: self._safe_window(),
                get_language=lambda: self.language,
                zone_key="buff_bar",
                tpl_keys=["buff_icon_shield", "buff_icon_blessedBody"],
                threshold=0.85,
                debug=True,
            ),
            enabled=True,
        )

        # --- workers / services ---
        self.postrow = PostTPRowRunner(
            controller=self.controller,
            server=self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            on_status=lambda msg, ok: print(msg),
        )
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

        # orchestrator + restart manager
        self.restart = RestartManager(
            controller=self.controller,
            get_server=lambda: self.server,
            get_window=lambda: self._safe_window(),
            get_language=lambda: self.language,
            watcher=self.watcher,
            account_getter=lambda: getattr(self, "account", {"login": "", "password": "", "pin": ""}),
            max_restart_attempts=3,
            retry_delay_s=1.0,
            logger=print,
        )
        self.orch = FlowOrchestrator(
            schedule=lambda fn, ms: self.root.after(ms, fn),
            log=print,
            checker=self.checker,
            watcher=self.watcher,
            to_village=self.to_village,
            postrow_runner=self.postrow,
            restart_manager=self.restart,
            get_server=lambda: self.server,
            get_language=lambda: self.language,
        )

        # --- UI placeholders (инициализируются в build_ui) ---
        self.afterbuff_ui = None
        self.afterbuff_runner = None
        self.buff = None
        self.tp = None

        # autobuff service (вкл/выкл управляет UI виджет)
        self.autobuff = AutobuffService(
            checker=self.checker,
            is_alive=lambda: self.watcher.is_alive(),
            buff_is_enabled=lambda: (self.buff and self.buff.is_enabled()) or False,
            buff_run_once=lambda: (self.buff and self.buff.run_once()) or False,
            on_charged_update=lambda v: setattr(self, "_charged_flag", v),
            tick_interval_s=1.0,
            log=print,
        )

        # rows controller (запустим после сборки UI)
        self.rows_ctrl: RowsController | None = None
        self._rows_menu: ttk.Combobox | None = None
        self._row_var = tk.StringVar(value="")
        self._rows_cache: list[tuple[str, str]] = []

        # ping arduino (по кнопке есть отдельный тест, тут — опционально)
        try:
            self.controller.send("ping")
            response = self.controller.read()
            print("[✓] Arduino ответила" if response == "pong" else "[×] Нет ответа")
        except Exception as e:
            print(f"[×] Ошибка связи с Arduino: {e}")

    # ---------------- helpers ----------------
    def _safe_window(self):
        try:
            return self.winprobe.current_window_info()
        except Exception:
            return None

    # ---------------- watcher → orchestrator ----------------
    def _on_dead_proxy(self, st):
        self.orch.on_dead(st)

    def _on_alive_proxy(self, st):
        self.orch.on_alive(st)

    # ---------------- UI build ----------------
    def build_ui(self, parent: tk.Widget, local_version: str):
        # Системный блок
        top = Collapsible(parent, "Системные настройки", opened=True)
        top.pack(fill="x", padx=8, pady=4)

        # язык
        lang_frame = tk.Frame(top.body())
        lang_frame.pack(pady=(5, 2), anchor="center")
        tk.Label(lang_frame, text="Язык интерфейса:", font=("Arial", 10)).pack(side="left", padx=(0, 6))
        ttk.OptionMenu(
            lang_frame, self.language_var, self.language_var.get(), "rus", "eng", command=self.set_language
        ).pack(side="left", padx=(0, 20))

        # сервер
        server_frame = tk.Frame(top.body()); server_frame.pack(pady=(2, 6), anchor="center")
        tk.Label(server_frame, text="Сервер:", font=("Arial", 10)).pack(side="left", padx=(0, 12))
        servers = list_servers() or ["l2mad"]
        if self.server not in servers:
            self.server = servers[0]; self.server_var.set(self.server)
        ttk.OptionMenu(
            server_frame, self.server_var, self.server_var.get(), *servers, command=self.set_server
        ).pack(side="left", padx=(0, 20))

        # окно
        window_frame = tk.Frame(top.body()); window_frame.pack(pady=(2, 10), anchor="center")
        tk.Button(window_frame, text="🔍 Найти окно Lineage", command=self.winprobe.try_find_window_again).pack(
            side="left", padx=(0, 8)
        )
        ws_label = tk.Label(top.body(), text="[?] Поиск окна...", font=("Arial", 9), fg="gray")
        ws_label.pack()
        self.winprobe.attach_status(ws_label)

        # связь
        self.driver_status = tk.Label(top.body(), text="Состояние связи: неизвестно", fg="gray")
        tk.Button(top.body(), text="🧪 Тест коннекта", command=lambda: run_test_command(self.controller, self.driver_status)).pack(pady=5)
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

        # аккаунт
        tk.Button(top.body(), text="Настроить аккаунт", command=self._open_account_dialog).pack(pady=(6, 2))

        # выход
        tk.Button(top.body(), text="Выход", fg="red", command=self.exit_program).pack(pady=10)

        # Рабочий поток
        flow = Collapsible(parent, "Отслеживать состояние · Баф · Макросы · ТП", opened=True)
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
        # BuffIntervalControl(
        #     flow.body(),
        #     checker=self.checker,
        #     on_toggle_autobuff=lambda en: self.autobuff.set_enabled(bool(en)),
        #     intervals=(1, 5, 10, 20),
        # )

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
            check_is_dead=lambda: (not self.watcher.is_alive()),
        )

        # передаём UI в оркестратор
        self.orch.set_ui(
            buff_is_enabled=lambda: self.buff.is_enabled(),
            buff_run_once=lambda: self.buff.run_once(),
            macros_ui_is_enabled=lambda: self.afterbuff_ui.is_enabled(),
            macros_ui_run_always=lambda: self.afterbuff_ui.run_always(),
            macros_ui_get_duration_s=lambda: self.afterbuff_ui.get_duration_s(),
            macros_run_once=lambda: self.afterbuff_runner.run_once(),
            tp_is_enabled=lambda: self.tp.is_enabled(),
            tp_teleport_now_selected=lambda: self.tp.teleport_now_selected(),
            tp_get_selected_destination=lambda: self.tp.get_selected_destination(),
            tp_get_selected_row_id=lambda: self.tp.get_selected_row_id(),
            respawn_ui_is_enabled=lambda: self.respawn_ui.is_enabled(),
        )

        # --- блок: маршрут после ТП ---
        rows_frame = tk.Frame(tp_frame)
        rows_frame.pack(fill="x", padx=6, pady=(4, 6), anchor="w")
        tk.Label(rows_frame, text="Маршрут после ТП:").pack(side="left", padx=(0, 8))
        self._rows_menu = ttk.Combobox(rows_frame, textvariable=self._row_var, state="readonly", width=28, values=[])
        self._rows_menu.pack(side="left")
        self._rows_menu.bind("<<ComboboxSelected>>", lambda *_: self._on_row_selected_from_ui())
        ttk.Button(rows_frame, text="Очистить", command=self._clear_row).pack(side="left", padx=6)

        # контроллер маршрутов
        self.rows_ctrl = RowsController(
            get_server=lambda: self.server,
            get_language=lambda: self.language,
            get_destination=lambda: self.tp.get_selected_destination(),
            schedule=lambda fn, ms: self.root.after(ms, fn),
            on_values=self._rows_set_values,
            on_select_row_id=lambda rid: self.tp.set_selected_row_id(rid or ""),
            log=print,
        )
        self.rows_ctrl.start()

        # авто-проверка обновлений периодически
        def _schedule_update_check():
            run_update_check(local_version, self.version_status_label, self.root, self)
            self.root.after(600_000, _schedule_update_check)

        _schedule_update_check()

    # ---------------- rows helpers ----------------
    def _rows_set_values(self, rows: list[tuple[str, str]]):
        """rows: [(row_id, title)]"""
        self._rows_cache = rows[:]
        titles = [t for (_id, t) in rows]
        try:
            self._rows_menu["values"] = titles
        except Exception:
            pass
        # синхронизировать отображаемый текст
        if not titles:
            self._row_var.set("")
        else:
            # если текущий невалиден — выбрать первый
            cur_id = self.tp.get_selected_row_id() or ""
            if cur_id and any(rid == cur_id for (rid, _t) in rows):
                # выставим соответствующий титул
                for rid, t in rows:
                    if rid == cur_id:
                        self._row_var.set(t)
                        break
            else:
                self._row_var.set(titles[0])

    def _row_id_from_title(self, title: str) -> str | None:
        for rid, t in self._rows_cache:
            if t == title:
                return rid
        return None

    def _on_row_selected_from_ui(self):
        rid = self._row_id_from_title(self._row_var.get() or "")
        try:
            self.tp.set_selected_row_id(rid or "")
        except Exception:
            pass

    def _clear_row(self):
        self._row_var.set("")
        self._on_row_selected_from_ui()

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

    # ---------------- setters ----------------
    def set_language(self, lang):
        self.language = (lang or "rus").lower()
        print(f"[UI] Язык интерфейса установлен: {self.language}")

    def set_server(self, server):
        self.server = (server or "l2mad").lower()
        print(f"[UI] Сервер установлен: {self.server}")
        self.profile = get_server_profile(self.server)

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

    # -----------------account settings -----------------------
    def _open_account_dialog(self):
        initial = getattr(self, "account", {"login": "", "password": "", "pin": ""})
        AccountSettingsDialog(self.root, initial=initial, on_save=self._save_account)

    def _save_account(self, data: dict):
        if not hasattr(self, "account") or not isinstance(self.account, dict):
            self.account = {"login": "", "password": "", "pin": ""}
        self.account.update({
            "login": data.get("login", ""),
            "password": data.get("password", ""),
            "pin": data.get("pin", ""),
        })
        print("[account] saved")

    # ---------------- window probe callbacks ----------------
    def _on_window_found(self, _win_info: dict):
        pass  # логика автозапуска профилированных тиков вынесена из launcher

    # ---------------- shutdown ----------------
    def exit_program(self):
        try:
            self.watcher.stop()
        except Exception:
            pass
        try:
            self.autobuff.stop()
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
    root.geometry("620x700")
    root.resizable(False, False)

    header = tk.Frame(root)
    header.pack(fill="x")
    tk.Label(header, text="Revive", font=("Arial", 20, "bold"), fg="orange").pack(pady=10)
    tk.Label(header, text="Функции:", font=("Arial", 12, "bold")).pack(pady=(5,))

    scroll = VScrollFrame(root)
    scroll.pack(fill="both", expand=True)

    parent = tk.Frame(scroll.interior); parent.pack(pady=10, fill="both", expand=True)

    app = ReviveLauncherUI(root)
    app.build_ui(parent, local_version)

    root.protocol("WM_DELETE_WINDOW", app.exit_program)
    logging.info("[launcher] loaded")
    root.mainloop()
