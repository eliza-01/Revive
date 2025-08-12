# app/ui/buff_controls.py
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable

from core.servers.registry import BUFF_METHOD_DASHBOARD, BUFF_METHOD_NPC

class BuffControls:
    def __init__(self, parent: tk.Widget, profile_getter: Callable, language_getter: Callable[[], str], window_found_getter: Callable[[], bool] = lambda: False):
        self._get_profile = profile_getter
        self._get_language = language_getter
        self._window_found = window_found_getter

        self.enabled_var = tk.BooleanVar(value=False)
        self.mode_var = tk.StringVar(value="profile")
        self.method_var = tk.StringVar(value=BUFF_METHOD_DASHBOARD)

        self.frame = tk.Frame(parent)
        self.frame.pack_forget()

        row1 = tk.Frame(self.frame); row1.pack(fill="x")
        self._cb = tk.Checkbutton(row1, text="Баф после респавна", font=("Arial", 11), variable=self.enabled_var, command=lambda: self._on_toggle(self.enabled_var.get()))
        self._cb.pack(side="left", padx=(0, 8))

        tk.Label(row1, text="Метод:", font=("Arial", 10)).pack(side="left", padx=(8, 4))
        self._method_menu = ttk.OptionMenu(row1, self.method_var, self.method_var.get(), command=lambda *_: None)
        self._method_menu.pack(side="left")

        row2 = tk.Frame(self.frame); row2.pack(fill="x", pady=(4,0))
        tk.Label(row2, text="Тип бафа:", font=("Arial", 10)).pack(side="left")
        self._mode = ttk.OptionMenu(row2, self.mode_var, self.mode_var.get(), "profile", "fighter", "mage", command=lambda *_: self._on_mode_change(self.mode_var.get()))
        self._mode.pack(side="left", padx=(6,0))

        self.refresh_enabled(self._get_profile())
        self._fill_method_menu()

    def pack(self, **kwargs):
        self.frame.pack(pady=2, **kwargs)

    def pack_forget(self):
        self.frame.pack_forget()

    def is_enabled(self) -> bool:
        return bool(self.enabled_var.get())

    def get_mode(self) -> str:
        return (self.mode_var.get() or "profile").lower()

    def get_method(self) -> str:
        return (self.method_var.get() or BUFF_METHOD_DASHBOARD).lower()

    def refresh_enabled(self, profile=None):
        profile = profile or self._get_profile()
        supports = getattr(profile, "supports_buffing", lambda: False)()
        if supports:
            self._cb.configure(state="normal"); self._mode.configure(state="normal"); self._method_menu.configure(state="normal")
        else:
            self.enabled_var.set(False)
            self._cb.configure(state="disabled"); self._mode.configure(state="disabled"); self._method_menu.configure(state="disabled")
        self._fill_method_menu()

    def _fill_method_menu(self):
        profile = self._get_profile()
        methods = []
        try:
            methods = profile.buff_supported_methods()
        except Exception:
            methods = [BUFF_METHOD_DASHBOARD]
        menu = self._method_menu["menu"]; menu.delete(0,"end")
        human = {BUFF_METHOD_DASHBOARD:"dashboard", BUFF_METHOD_NPC:"npc"}
        for m in methods:
            menu.add_command(label=human.get(m,m), command=lambda v=m: self.method_var.set(v))
        if methods:
            self.method_var.set(methods[0])

    def _on_toggle(self, enabled: bool):
        profile = self._get_profile()
        supports = getattr(profile, "supports_buffing", lambda: False)()
        if not supports:
            print("[UI] Для этого сервера автобаф не поддерживается."); self.enabled_var.set(False); return
        if not self._window_found():
            print("[UI] Окно не найдено, автобаф не запущен."); self.enabled_var.set(False); return
        print("[UI] Автобаф ВКЛ" if enabled else "[UI] Автобаф ВЫКЛ")

    def _on_mode_change(self, mode: str):
        profile = self._get_profile()
        if hasattr(profile, "set_buff_mode"):
            profile.set_buff_mode(mode or "profile")
        if hasattr(profile, "get_buff_mode"):
            print(f"[UI] Тип бафа: {profile.get_buff_mode()}")
