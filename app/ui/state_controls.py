# app/ui/state_controls.py
import tkinter as tk
from typing import Callable

class StateControls:
    """
    Чекбокс отслеживания состояния персонажа (HP).
    По умолчанию включён. При выключении — вызывает stop_fn.
    """
    def __init__(self, parent: tk.Widget, start_fn: Callable[[], None], stop_fn: Callable[[], None]):
        self.enabled_var = tk.BooleanVar(value=True)
        self._start = start_fn
        self._stop = stop_fn

        frame = tk.Frame(parent)
        frame.pack(pady=(2, 6), anchor="w")
        self._cb = tk.Checkbutton(
            frame,
            text="Отслеживать состояние (HP)",
            font=("Arial", 10),
            variable=self.enabled_var,
            command=self._on_toggle,
        )
        self._cb.pack(side="left")

        # запуск мониторинга сразу
        try:
            self._start()
        except Exception:
            pass

    def _on_toggle(self):
        try:
            if self.enabled_var.get():
                self._start()
            else:
                self._stop()
        except Exception:
            pass
