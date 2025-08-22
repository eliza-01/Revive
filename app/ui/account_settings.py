# app/ui/account_settings.py
import tkinter as tk
import tkinter.ttk as ttk

class AccountSettingsDialog(tk.Toplevel):
    def __init__(self, parent, initial: dict, on_save):
        super().__init__(parent)
        self.title("Настройки аккаунта")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_save = on_save
        login = initial.get("login", "")
        password = initial.get("password", "")
        pin = initial.get("pin", "")

        frm = tk.Frame(self, padx=10, pady=10); frm.pack(fill="both")

        tk.Label(frm, text="Логин:").grid(row=0, column=0, sticky="e", padx=(0,6), pady=4)
        self.login_var = tk.StringVar(value=login)
        tk.Entry(frm, textvariable=self.login_var, width=28).grid(row=0, column=1, pady=4)

        tk.Label(frm, text="Пароль:").grid(row=1, column=0, sticky="e", padx=(0,6), pady=4)
        self.pass_var = tk.StringVar(value=password)
        tk.Entry(frm, textvariable=self.pass_var, width=28, show="•").grid(row=1, column=1, pady=4)

        tk.Label(frm, text="PIN (цифры):").grid(row=2, column=0, sticky="e", padx=(0,6), pady=4)
        self.pin_var = tk.StringVar(value=pin)
        e = tk.Entry(frm, textvariable=self.pin_var, width=28)
        e.grid(row=2, column=1, pady=4)
        e.configure(validate="key", validatecommand=(e.register(lambda s: s.isdigit() or s == ""), "%P"))

        btns = tk.Frame(frm); btns.grid(row=3, column=0, columnspan=2, pady=(10,0))
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="right", padx=(0,6))

        self.bind("<Return>", lambda *_: self._save())
        self.bind("<Escape>", lambda *_: self.destroy())

    def _save(self):
        data = {
            "login": self.login_var.get().strip(),
            "password": self.pass_var.get(),
            "pin": self.pin_var.get().strip(),
        }
        try:
            self._on_save(data)
        finally:
            self.destroy()
