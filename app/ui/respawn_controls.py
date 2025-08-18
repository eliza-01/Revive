# app/ui/respawn_controls.py
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable

class RespawnControls:
    """
    Блок «Отслеживание и подъём» + внутр. контейнер для дочерних панелей.
    Публично: is_monitoring(), is_enabled(), get_body()
    """
    def __init__(self, parent: tk.Widget, start_fn: Callable[[], None], stop_fn: Callable[[], None]):
        self._start = start_fn
        self._stop = stop_fn

        frame = tk.LabelFrame(parent, text="Отслеживание и подъём")
        frame.pack(fill="x", padx=6, pady=6, anchor="w")
        self._frame = frame

        row1 = tk.Frame(frame); row1.pack(fill="x", pady=(2, 2), anchor="w")
        self._monitor_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row1,
            text="Отслеживать состояние (включить StateWatcher)",
            variable=self._monitor_var,
            command=self._on_toggle_monitor,
            font=("Arial", 12, "bold"),
            fg="orange",
            selectcolor="lightyellow",
        ).pack(side="left", padx=4, pady=2)

        row2 = tk.Frame(frame); row2.pack(fill="x", pady=(2, 2), anchor="w")
        self._enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            row2,
            text="Встать после смерти (нажать «В деревню»)",
            variable=self._enabled_var,
            font=("Arial", 10),
        ).pack(side="left")

        self._status = tk.Label(frame, text="Мониторинг: выкл", fg="gray")
        self._status.pack(anchor="w", pady=(4, 2))

        # Внутренний контейнер для доп. панелей (сюда поместим «Состояние персонажа»)
        self._body = tk.Frame(frame)
        self._body.pack(fill="x", pady=(6, 2), anchor="w")

    def _on_toggle_monitor(self):
        try:
            if self._monitor_var.get():
                self._start(); self._status.config(text="Мониторинг: вкл", fg="green")
            else:
                self._stop();  self._status.config(text="Мониторинг: выкл", fg="gray")
        except Exception:
            self._status.config(text="Ошибка переключения", fg="red")

    def is_monitoring(self) -> bool:
        return bool(self._monitor_var.get())

    def is_enabled(self) -> bool:
        return bool(self._enabled_var.get())

    def get_body(self) -> tk.Frame:
        return self._body
