# _archive/app/ui/tp_controls.py
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Optional, Tuple

from _archive.core.features.teleport_after_respawn import (
    TeleportAfterDeathWorker,
    Teleport_METHOD_DASHBOARD,
    Teleport_METHOD_GATEKEEPER,
)
from _archive.servers import get_categories, get_locations


class TeleportControls:
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
        self.method_var = tk.StringVar(value=Teleport_METHOD_DASHBOARD)
        self.category_var = tk.StringVar(value="")  # stores category_id
        self.location_var = tk.StringVar(value="")  # stores location_id

        self._selected_row_id: str = ""  # external UI may set via set_selected_row_id()

        self.frame = tk.Frame(parent)
        self.frame.pack(pady=(8, 2), anchor="w", fill="x")

        cb = tk.Checkbutton(
            self.frame,
            text="ТП после смерти",
            font=("Arial", 11),
            variable=self.enabled_var,
            command=self._on_toggle,
        )
        cb.pack(anchor="w")

        row = tk.Frame(self.frame)
        row.pack(fill="x", pady=(4, 0))

        tk.Label(row, text="Метод:", font=("Arial", 10)).pack(side="left")
        self.method_menu = ttk.OptionMenu(
            row,
            self.method_var,
            self.method_var.get(),
            Teleport_METHOD_DASHBOARD,
            Teleport_METHOD_GATEKEEPER,
            command=lambda *_: None,
        )
        self.method_menu.pack(side="left", padx=(6, 16))

        tk.Label(row, text="Категория:", font=("Arial", 10)).pack(side="left")
        self.category_menu = ttk.OptionMenu(
            row,
            self.category_var,
            "",
            command=lambda *_: self._on_category_change(self.category_var.get()),
        )
        self.category_menu.pack(side="left", padx=(6, 16))

        tk.Label(row, text="Локация:", font=("Arial", 10)).pack(side="left")
        self.location_menu = ttk.OptionMenu(
            row,
            self.location_var,
            "",
            command=lambda *_: None,
        )
        self.location_menu.pack(side="left", padx=(6, 0))

        self.status = tk.Label(
            self.frame, text="Выберите категорию и локацию", fg="gray", font=("Arial", 9)
        )
        self.status.pack(anchor="w", pady=(4, 2))

        self._fill_categories()
        self._worker: Optional[TeleportAfterDeathWorker] = None

    # ------- public API used by launcher -------

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def is_enabled(self) -> bool:
        return bool(self.enabled_var.get())

    def selection(self) -> Tuple[str, str, str]:
        return self.category_var.get(), self.location_var.get(), self.method_var.get()

    def get_selected_destination(self) -> Tuple[str, str]:
        """Return (village_id, location_id)."""
        return self.category_var.get() or "", self.location_var.get() or ""

    def set_selected_row_id(self, row_id: str) -> None:
        self._selected_row_id = row_id or ""

    def get_selected_row_id(self) -> str:
        return self._selected_row_id

    def teleport_now_selected(self) -> bool:
        w = self._ensure_worker()
        cat = self.category_var.get()
        loc = self.location_var.get()
        method = self.method_var.get()
        w.configure(cat, loc, method)
        return w.teleport_now(cat, loc, method)

    # ------- internals -------

    def _ensure_worker(self) -> TeleportAfterDeathWorker:
        if self._worker is None:
            def _status(text, ok=None):
                try:
                    self.status.config(
                        text=text,
                        fg=("green" if ok else ("red" if ok is False else "gray")),
                    )
                except Exception:
                    print(text)

            self._worker = TeleportAfterDeathWorker(
                controller=self.controller,
                window_info=self.get_window_info(),
                get_language=self.get_language,
                on_status=_status,
                check_is_dead=self._check_is_dead,
            )
        # refresh dynamic fields each call
        self._worker.window = self.get_window_info()
        self._worker.set_method(self.method_var.get())
        return self._worker

    def _on_toggle(self):
        if self.enabled_var.get():
            self.frame.pack()
            self.status.config(text="Выберите категорию и локацию", fg="gray")
        else:
            self.status.config(text="Отключено", fg="gray")

    def _fill_categories(self):
        cats = get_categories(lang=self.get_language())
        menu = self.category_menu["menu"]
        menu.delete(0, "end")
        menu.add_command(
            label="— не выбрано —",
            command=lambda: (self.category_var.set(""), self._on_category_change("")),
        )
        for c in cats:
            cid = c["id"]
            label = c["display_rus"] if (self.get_language() == "rus") else c["display_eng"]
            menu.add_command(
                label=label,
                command=lambda v=cid: (self.category_var.set(v), self._on_category_change(v)),
            )
        self.category_var.set("")
        self._fill_locations([])

    def _fill_locations(self, locs):
        menu = self.location_menu["menu"]
        menu.delete(0, "end")
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
