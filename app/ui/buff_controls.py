# app/ui/buff_controls.py
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable

class BuffControls:
    """
    UI-блок "Баф после респавна".
    Внешние зависимости передаются функциями:
      - profile_getter(): объект профиля сервера
      - language_getter(): текущий язык ("rus"/"eng")
      - window_found_getter(): True/False — найдено ли окно клиента
    """
    def __init__(
            self,
            parent: tk.Widget,
            profile_getter: Callable,
            language_getter: Callable[[], str],
            window_found_getter: Callable[[], bool] = lambda: False,
    ):
        self._get_profile = profile_getter
        self._get_language = language_getter
        self._window_found = window_found_getter

        self.enabled_var = tk.BooleanVar(value=False)
        self.mode_var = tk.StringVar(value="profile")  # "profile" | "fighter" | "mage"

        self.frame = tk.Frame(parent)
        # по умолчанию скрыт. Родитель показывает, когда включён автоподъём.
        self.frame.pack_forget()

        self._cb = tk.Checkbutton(
            self.frame,
            text="Баф после респавна",
            font=("Arial", 11),
            variable=self.enabled_var,
            command=lambda: self._on_toggle(self.enabled_var.get()),
        )
        self._cb.pack(side="left", padx=(0, 8))

        self._mode = ttk.OptionMenu(
            self.frame,
            self.mode_var,
            self.mode_var.get(),
            "profile", "fighter", "mage",
            command=lambda *_: self._on_mode_change(self.mode_var.get()),
        )
        self._mode.pack(side="left")

        # начальная доступность
        self.refresh_enabled(self._get_profile())

    # ---------- public API ----------
    def pack(self, **kwargs):
        self.frame.pack(pady=2, **kwargs)

    def pack_forget(self):
        self.frame.pack_forget()

    def is_enabled(self) -> bool:
        return bool(self.enabled_var.get())

    def get_mode(self) -> str:
        return (self.mode_var.get() or "profile").lower()

    def refresh_enabled(self, profile=None):
        profile = profile or self._get_profile()
        supports = getattr(profile, "supports_buffing", lambda: False)()
        if supports:
            self._cb.configure(state="normal")
            self._mode.configure(state="normal")
        else:
            # выключаем и блокируем
            self.enabled_var.set(False)
            self._cb.configure(state="disabled")
            self._mode.configure(state="disabled")

    # ---------- internals ----------
    def _on_toggle(self, enabled: bool):
        profile = self._get_profile()
        supports = getattr(profile, "supports_buffing", lambda: False)()
        if not supports:
            print("[UI] Для этого сервера автобаф не поддерживается.")
            self.enabled_var.set(False)
            return
        if not self._window_found():
            print("[UI] Окно не найдено, автобаф не запущен.")
            self.enabled_var.set(False)
            return
        print("[UI] Автобаф ВКЛ" if enabled else "[UI] Автобаф ВЫКЛ")

    def _on_mode_change(self, mode: str):
        profile = self._get_profile()
        if hasattr(profile, "set_buff_mode"):
            profile.set_buff_mode(mode or "profile")
        if hasattr(profile, "get_buff_mode"):
            print(f"[UI] Тип бафа: {profile.get_buff_mode()}")
        else:
            print(f"[UI] Тип бафа: {mode}")
