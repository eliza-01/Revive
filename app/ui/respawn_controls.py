# app/ui/respawn_controls.py
import tkinter as tk
from typing import Callable

class RespawnControls:
    """
    Чекбокс автоподъёма (0% HP → В деревню).
    По умолчанию включён. Вызывает start_fn/stop_fn.
    """
    def __init__(self, parent: tk.Widget, start_fn: Callable[[], None], stop_fn: Callable[[], None]):
        self._start = start_fn
        self._stop = stop_fn
        self.enabled_var = tk.BooleanVar(value=True)

        frame = tk.Frame(parent)
        frame.pack(pady=(2, 6), anchor="w")
        tk.Checkbutton(
            frame,
            text="Мониторинг HP + автоподъём (0% → В деревню)",
            font=("Arial", 10),
            variable=self.enabled_var,
            command=self._on_toggle,
        ).pack(side="left")

        # старт сразу
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
