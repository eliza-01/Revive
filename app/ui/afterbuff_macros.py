import tkinter as tk
import tkinter.ttk as ttk

# только цифры, 0 идёт после 9
_ALLOWED = tuple("1234567890")

class AfterBuffMacrosControls:
    def __init__(self, parent: tk.Widget):
        self.enabled_var = tk.BooleanVar(value=False)
        self._rows = []

        frame = tk.LabelFrame(parent, text="Макросы после бафа")
        frame.pack(fill="x", padx=6, pady=6, anchor="w")
        self._frame = frame

        top = tk.Frame(frame); top.pack(fill="x", pady=(2, 2), anchor="w")
        tk.Checkbutton(top, text="Включить", variable=self.enabled_var).pack(side="left")
        tk.Button(top, text="+", width=2, command=self._add_row).pack(side="left", padx=(8, 0))

        self.always_var = tk.BooleanVar(value=False)
        tk.Checkbutton(top, text="Запускать даже без бафа", variable=self.always_var).pack(side="left", padx=(8, 0))

        self._rows_frame = tk.Frame(frame); self._rows_frame.pack(fill="x", pady=(4, 2), anchor="w")
        self._add_row()

        row_delay = tk.Frame(frame); row_delay.pack(fill="x", pady=(4, 2), anchor="w")
        tk.Label(row_delay, text="Задержка между макросами, мс:").pack(side="left")
        self.delay_entry = tk.Entry(row_delay, width=6)
        self.delay_entry.insert(0, "300")
        self.delay_entry.pack(side="left", padx=(6, 0))

        row_dur = tk.Frame(frame); row_dur.pack(fill="x", pady=(4, 2), anchor="w")
        tk.Label(row_dur, text="Время на выполнение макросов, сек:").pack(side="left")
        self.duration_entry = tk.Entry(row_dur, width=6)
        self.duration_entry.insert(0, "2")
        self.duration_entry.pack(side="left", padx=(6, 0))

    def run_always(self) -> bool:
        return bool(self.always_var.get())

    def _add_row(self):
        row = tk.Frame(self._rows_frame); row.pack(anchor="w", pady=2)
        var = tk.StringVar(value=_ALLOWED[0])
        ttk.OptionMenu(row, var, var.get(), *_ALLOWED).pack(side="left")
        tk.Button(row, text="−", width=2, command=lambda: self._remove_row(row, var)).pack(side="left", padx=(6, 0))
        self._rows.append((row, var))

    def _remove_row(self, row, var):
        if len(self._rows) <= 1:
            return
        row.destroy()
        self._rows = [(r, v) for (r, v) in self._rows if v is not var]

    # ---- API ----
    def is_enabled(self) -> bool:
        return bool(self.enabled_var.get())

    def get_sequence(self):
        return [v.get() for (_, v) in self._rows]

    def get_delay_ms(self) -> int:
        try:
            return int(self.delay_entry.get().strip())
        except Exception:
            return 0

    def get_duration_s(self) -> float:
        try:
            return max(0.0, float(self.duration_entry.get().strip()))
        except Exception:
            return 0.0
