import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Iterable

class BuffIntervalControl:
    """
    «Проверять баф каждые: ... минут» + «Автобаф по интервалу».
    """
    def __init__(
            self,
            parent: tk.Widget,
            checker,
            on_toggle_autobuff: Callable[[bool], None],
            intervals: Iterable[int] = (1, 5, 10, 20),
    ):
        self._checker = checker
        self._intervals = tuple(int(x) for x in intervals)

        frame = tk.LabelFrame(parent, text="Проверка бафа")
        frame.pack(fill="x", padx=6, pady=6, anchor="w")

        row = tk.Frame(frame); row.pack(fill="x", pady=(2, 2), anchor="w")
        ttk.Label(row, text="Проверять каждые:").pack(side="left", padx=(0, 6))

        self._val = tk.StringVar(value=str(self._intervals[0]))
        choices = [str(x) for x in self._intervals]
        ttk.OptionMenu(row, self._val, self._val.get(), *choices, command=self._on_interval_change).pack(side="left", padx=(0, 8))

        self._auto_var = tk.BooleanVar(value=False)  # дефолт OFF
        tk.Checkbutton(
            row,
            text="Автобаф по интервалу",
            variable=self._auto_var,
            command=lambda: on_toggle_autobuff(self._auto_var.get())
        ).pack(side="left", padx=(12, 0))

        self._on_interval_change(self._val.get())

    def _on_interval_change(self, val: str):
        try:
            self._checker.set_interval_minutes(int(val))
            self._checker.set_enabled(True)
        except Exception:
            pass
