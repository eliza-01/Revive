# _archive/app/ui/state_controls.py
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Any

class StateControls:
    """
    Панель состояния. Раз в 2 секунды берёт last() из StateWatcher и обновляет HP/CP.
    Никакого доп. захвата экрана.
    """
    def __init__(self, parent: tk.Widget, state_getter: Callable[[], Any]):
        self._get = state_getter

        frame = tk.LabelFrame(parent, text="Состояние персонажа")
        frame.pack(fill="x", padx=6, pady=6, anchor="w")

        row = tk.Frame(frame); row.pack(fill="x", pady=(2, 2), anchor="w")
        tk.Label(row, text="HP:", font=("Arial", 10)).pack(side="left")
        self._hp_lbl = tk.Label(row, text="-- %", font=("Arial", 10), fg="gray")
        self._hp_lbl.pack(side="left", padx=(4, 12))

        tk.Label(row, text="CP:", font=("Arial", 10)).pack(side="left")
        self._cp_lbl = tk.Label(row, text="-- %", font=("Arial", 10), fg="gray")
        self._cp_lbl.pack(side="left", padx=(4, 12))

        frame.after(2000, self._tick)

    def _tick(self):
        try:
            st = self._get()  # ожидается PlayerState от watcher.last()
            hp_ratio = float(getattr(st, "hp_ratio", 0.0) or 0.0)
            hp = max(0, min(100, int(round(hp_ratio * 100))))
            self._hp_lbl.config(text=f"{hp} %", fg=("green" if hp > 50 else "orange" if hp > 15 else "red"))
            self._cp_lbl.config(text="100 %", fg="gray")  # CP заглушка
        except Exception:
            self._hp_lbl.config(text="-- %", fg="gray")
            self._cp_lbl.config(text="-- %", fg="gray")
        self._hp_lbl.after(2000, self._tick)
