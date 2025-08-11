# app/ui/tp_controls.py
import threading
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Optional

from core.features.tp_after_death import TPAfterDeathWorker, TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER
from core.servers.l2mad.locations_map import get_categories, get_locations

class TPControls:
    def __init__(
            self,
            parent: tk.Widget,
            controller,
            get_language: Callable[[], str],
            get_window_info: Callable[[], Optional[dict]],
            profile_getter: Callable,
            check_is_dead: Optional[Callable[[], bool]] = None,
            focus_game_window: Optional[Callable] = None,
    ):
        self._controller = controller
        self._get_language = get_language
        self._get_window_info = get_window_info
        self._get_profile = profile_getter
        self._worker: Optional[TPAfterDeathWorker] = None
        self._tp_running = False
        self._tp_thread: Optional[threading.Thread] = None
        self.enabled_var = tk.BooleanVar(value=False)
        self.method_var = tk.StringVar(value=TP_METHOD_DASHBOARD)
        self.category_id = tk.StringVar(value="")
        self.location_id = tk.StringVar(value="")
        self.category_id.trace_add("write", lambda *_: self.on_category_change(self.category_id.get()))
        self.location_id.trace_add("write", lambda *_: self.on_location_change(self.location_id.get()))
        self.frame_outer = tk.Frame(parent)
        top_row = tk.Frame(self.frame_outer); top_row.pack(fill="x")
        self.checkbox = tk.Checkbutton(top_row, text="ТП после смерти", font=("Arial", 11), variable=self.enabled_var, command=lambda: self.on_toggle(self.enabled_var.get()))
        self.checkbox.pack(side="left", pady=(6, 2))
        tk.Label(top_row, text="Метод:", font=("Arial", 10)).pack(side="left", padx=(12, 4))
        self.method_menu = ttk.OptionMenu(top_row, self.method_var, self.method_var.get(), command=lambda _: self.on_method_change(self.method_var.get()))
        self.method_menu.pack(side="left", pady=(6, 2))
        self.frame_inner = tk.Frame(self.frame_outer)
        self.frame_inner.pack(pady=(8, 2))
        self.frame_inner.pack_forget()
        row = tk.Frame(self.frame_inner); row.pack(fill="x", pady=(2, 0))
        tk.Label(row, text="Категория:", font=("Arial", 10)).pack(side="left")
        self.category_menu = ttk.OptionMenu(row, self.category_id, "", command=lambda _: self.on_category_change(self.category_id.get()))
        self.category_menu.pack(side="left", padx=(6, 16))
        tk.Label(row, text="Локация:", font=("Arial", 10)).pack(side="left")
        self.location_menu = ttk.OptionMenu(row, self.location_id, "", command=lambda _: self.on_location_change(self.location_id.get()))
        self.location_menu.pack(side="left", padx=(6, 0))
        self.status_label = tk.Label(self.frame_inner, text="Выберите метод, категорию и локацию", fg="gray", font=("Arial", 9))
        self.status_label.pack(anchor="w", pady=(4, 2))
        self._fill_method_menu()
        self._fill_category_menu()
        self._external_check_is_dead = check_is_dead
        self._external_focus_game_window = focus_game_window

    def pack(self, **kwargs):
        self.frame_outer.pack(**kwargs)

    def pack_forget(self):
        self.frame_outer.pack_forget()

    def is_enabled(self) -> bool:
        return bool(self.enabled_var.get())

    def selection(self):
        return self.category_id.get(), self.location_id.get(), self.method_var.get()

    def start_if_ready(self):
        if self._selection_valid():
            self._ensure_worker()
            self._worker.configure(self.category_id.get(), self.location_id.get(), self.method_var.get())
            self._worker.start()

    def stop(self):
        if self._worker:
            self._worker.stop()

    def configure(self, category_id: str, location_id: str, method: Optional[str] = None):
        if method:
            self.method_var.set(method)
        self.category_id.set(category_id or "")
        self.location_id.set(location_id or "")

    def teleport_now_selected(self) -> bool:
        if not self._worker or not self._selection_valid():
            return False
        try:
            self._worker.validate_templates(self.category_id.get(), self.location_id.get(), self.method_var.get())
            return bool(self._worker.teleport_now(self.category_id.get(), self.location_id.get(), self.method_var.get()))
        except Exception as e:
            print(f"[tp] Ошибка немедленного ТП: {e}")
            return False

    def on_toggle(self, enabled: bool):
        if enabled:
            self.frame_inner.pack(pady=(8, 2))
            self._set_status("Выберите метод, категорию и локацию", None)
            self.start_if_ready()
        else:
            self.frame_inner.pack_forget()
            self.stop()

    def on_method_change(self, method: str):
        avail = self._available_methods()
        if method not in avail and avail:
            self.method_var.set(avail[0])
        self.start_if_ready()

    def on_category_change(self, category_id: str):
        print(f"[TP] Выбрана категория id='{category_id}'")
        locs = get_locations(category_id) if category_id else []
        print(f"[TP] Локаций найдено: {len(locs)} -> {[l.get('id') for l in locs]}")
        self._fill_location_menu(locs)
        self.start_if_ready()

    def on_location_change(self, _location_id: str):
        self.start_if_ready()

    def _selection_valid(self) -> bool:
        return bool(self.enabled_var.get() and self.category_id.get() and self.location_id.get())

    def _available_methods(self):
        profile = self._get_profile()
        try:
            methods = profile.tp_supported_methods()
            methods = [m for m in methods if m in (TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER)]
            return methods or [TP_METHOD_DASHBOARD]
        except Exception:
            return [TP_METHOD_DASHBOARD]

    def _fill_method_menu(self):
        menu = self.method_menu["menu"]; menu.delete(0, "end")
        methods = self._available_methods()
        human = {TP_METHOD_DASHBOARD: "dashboard", TP_METHOD_GATEKEEPER: "gatekeeper"}
        for m in methods:
            menu.add_command(label=human.get(m, m), command=lambda v=m: self.method_var.set(v))
        self.method_var.set(methods[0])

    def _fill_category_menu(self):
        cats = get_categories()
        lang = self._get_language()
        menu = self.category_menu["menu"]; menu.delete(0, "end")
        menu.add_command(label="— не выбрано —", command=lambda: (self.category_id.set(""), self.on_category_change("")))
        for c in cats:
            cid = c["id"]
            label = c["display_rus"] if lang == "rus" else c["display_eng"]
            menu.add_command(label=label, command=lambda v=cid: (self.category_id.set(v), self.on_category_change(v)))
        self.category_id.set("")
        self._fill_location_menu([])

    def _fill_location_menu(self, locs):
        lang = self._get_language()
        menu = self.location_menu["menu"]; menu.delete(0, "end")
        menu.add_command(label="— не выбрано —", command=lambda: (self.location_id.set(""), self.on_location_change("")))
        for loc in locs:
            lid = loc["id"]
            label = loc["display_rus"] if lang == "rus" else loc["display_eng"]
            menu.add_command(label=label, command=lambda v=lid: (self.location_id.set(v), self.on_location_change(v)))
        self.location_id.set("")

    def _ensure_worker(self):
        if self._worker is not None:
            self._worker.window = self._get_window_info()
            self._worker.set_method(self.method_var.get())
            return self._worker
        def _status(text, ok=None):
            try:
                self._set_status(text, ok)
            except Exception:
                print(text)
        self._worker = TPAfterDeathWorker(
            controller=self._controller,
            window_info=self._get_window_info(),
            get_language=self._get_language,
            on_status=_status,
        )
        if self._external_check_is_dead:
            self._worker.check_is_dead = self._external_check_is_dead
        if self._external_focus_game_window:
            self._worker.focus_game_window = self._external_focus_game_window
        self._worker.set_method(self.method_var.get())
        return self._worker

    def _set_status(self, text: str, ok: Optional[bool]):
        color = "green" if ok else ("red" if ok is False else "gray")
        self.status_label.config(text=text, fg=color)
