# app/ui/tp_controls.py
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Optional, Tuple

from core.features.tp_after_respawn import TPAfterDeathWorker, TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER
from core.servers.l2mad.locations_map import get_categories, get_locations

class TPControls:
    def __init__(
            self,
            parent: tk.Widget,
            controller,
            get_language: Callable[[], str],
            get_window_info: Callable[[], Optional[dict]],
            profile_getter: Callable,
            check_is_dead: Callable[[], bool],
    ):
        self.parent = parent
        self.controller = controller
        self.get_language = get_language
        self.get_window_info = get_window_info
        self._get_profile = profile_getter
        self._check_is_dead = check_is_dead

        self.enabled_var = tk.BooleanVar(value=False)
        self.method_var = tk.StringVar(value=TP_METHOD_DASHBOARD)
        self.category_var = tk.StringVar(value="")
        self.location_var = tk.StringVar(value="")

        self.frame = tk.Frame(parent)
        self.frame.pack(pady=(8, 2), anchor="w", fill="x")

        cb = tk.Checkbutton(self.frame, text="ТП после смерти", font=("Arial", 11), variable=self.enabled_var, command=self._on_toggle)
        cb.pack(anchor="w")

        row = tk.Frame(self.frame); row.pack(fill="x", pady=(4,0))
        tk.Label(row, text="Метод:", font=("Arial", 10)).pack(side="left")
        self.method_menu = ttk.OptionMenu(row, self.method_var, self.method_var.get(), TP_METHOD_DASHBOARD, TP_METHOD_GATEKEEPER, command=lambda *_: None)
        self.method_menu.pack(side="left", padx=(6, 16))

        tk.Label(row, text="Категория:", font=("Arial", 10)).pack(side="left")
        self.category_menu = ttk.OptionMenu(row, self.category_var, "", command=lambda *_: self._on_category_change(self.category_var.get()))
        self.category_menu.pack(side="left", padx=(6, 16))

        tk.Label(row, text="Локация:", font=("Arial", 10)).pack(side="left")
        self.location_menu = ttk.OptionMenu(row, self.location_var, "", command=lambda *_: None)
        self.location_menu.pack(side="left", padx=(6, 0))

        self.status = tk.Label(self.frame, text="Выберите категорию и локацию", fg="gray", font=("Arial", 9))
        self.status.pack(anchor="w", pady=(4, 2))

        self._fill_categories()

        self._worker: Optional[TPAfterDeathWorker] = None

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def is_enabled(self) -> bool:
        return bool(self.enabled_var.get())

    def selection(self) -> Tuple[str, str, str]:
        return self.category_var.get(), self.location_var.get(), self.method_var.get()

    def _ensure_worker(self) -> TPAfterDeathWorker:
        if self._worker is None:
            def _status(text, ok=None):
                try:
                    self.status.config(text=text, fg=("green" if ok else ("red" if ok is False else "gray")))
                except Exception:
                    print(text)
            self._worker = TPAfterDeathWorker(
                controller=self.controller,
                window_info=self.get_window_info(),
                get_language=self.get_language,
                on_status=_status,
                check_is_dead=self._check_is_dead,  # ← добавить сюда
                # wait_alive_timeout_s=10.0,        # (опционально) настроить таймаут ожидания оживления
            )
        self._worker.window = self.get_window_info()
        self._worker.set_method(self.method_var.get())
        return self._worker

    def teleport_now_selected(self) -> bool:
        w = self._ensure_worker()
        w.configure(self.category_var.get(), self.location_var.get(), self.method_var.get())
        return w.teleport_now(self.category_var.get(), self.location_var.get(), self.method_var.get())

    # ----- UI events -----
    def _on_toggle(self):
        if self.enabled_var.get():
            self.frame.pack()
            self.status.config(text="Выберите категорию и локацию", fg="gray")
        else:
            self.status.config(text="Отключено", fg="gray")

    def _fill_categories(self):
        cats = get_categories(lang=self.get_language())
        menu = self.category_menu["menu"]; menu.delete(0, "end")
        menu.add_command(label="— не выбрано —", command=lambda: (self.category_var.set(""), self._on_category_change("")))
        for c in cats:
            cid = c["id"]
            label = c["display_rus"] if (self.get_language() == "rus") else c["display_eng"]
            menu.add_command(label=label, command=lambda v=cid: (self.category_var.set(v), self._on_category_change(v)))
        self.category_var.set("")
        self._fill_locations([])

    def _fill_locations(self, locs):
        menu = self.location_menu["menu"]; menu.delete(0, "end")
        menu.add_command(label="— не выбрано —", command=lambda: self.location_var.set(""))
        for loc in locs:
            lid = loc["id"]
            label = loc["display_rus"] if (self.get_language() == "rus") else loc["display_eng"]
            menu.add_command(label=label, command=lambda v=lid: self.location_var.set(v))
        self.location_var.set("")

    def _on_category_change(self, category_id: str):
        if not category_id:
            self._fill_locations([])
            return
        locs = get_locations(category_id, lang=self.get_language())
        self._fill_locations(locs)
