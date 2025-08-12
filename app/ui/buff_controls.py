# app/ui/buff_controls.py
import tkinter as tk
import tkinter.ttk as ttk
from typing import Callable, Optional

from core.features.buff_after_respawn import (
    BuffAfterRespawnWorker,
    BUFF_MODE_PROFILE,
    BUFF_MODE_MAGE,
    BUFF_MODE_FIGHTER,
)

class BuffControls:
    """
    UI блок "Баф после респавна".

    Публичный интерфейс:
      - is_enabled() -> bool
      - run_once() -> bool                     # запускает цикл бафа (flow) один раз
      - refresh_enabled(profile) -> None       # включает/отключает блок по поддержке профилем
      - set_mode(mode) -> None                 # 'profile' | 'mage' | 'fighter'
    """
    def __init__(
            self,
            parent: tk.Widget,
            controller,
            server_getter: Callable[[], str],
            language_getter: Callable[[], str],
            get_window: Callable[[], Optional[dict]],
            profile_getter: Callable[[], object],
            window_found_getter: Callable[[], bool],
    ):
        self.parent = parent
        self._controller = controller
        self._get_server = server_getter
        self._get_language = language_getter
        self._get_window = get_window
        self._get_profile = profile_getter
        self._window_found = window_found_getter

        self.enabled_var = tk.BooleanVar(value=False)
        self.mode_var = tk.StringVar(value=BUFF_MODE_PROFILE)

        frame = tk.LabelFrame(parent, text="Баф после респавна")
        frame.pack(fill="x", padx=6, pady=6, anchor="w")
        self._frame = frame

        row = tk.Frame(frame); row.pack(fill="x", pady=(2, 2), anchor="w")

        cb = tk.Checkbutton(
            row,
            text="Включить баф",
            variable=self.enabled_var,
            command=self._on_toggle,
            font=("Arial", 10),
        )
        cb.pack(side="left", padx=(0, 10))

        ttk.Label(row, text="Режим:").pack(side="left")
        self._mode_menu = ttk.OptionMenu(
            row,
            self.mode_var,
            self.mode_var.get(),
            BUFF_MODE_PROFILE,
            BUFF_MODE_MAGE,
            BUFF_MODE_FIGHTER,
            command=lambda *_: self._on_mode_change(self.mode_var.get()),
        )
        self._mode_menu.pack(side="left", padx=(6, 0))

        self._status = tk.Label(frame, text="Отключено", fg="gray")
        self._status.pack(anchor="w", pady=(4, 2))

        # worker создаём лениво
        self._worker: Optional[BuffAfterRespawnWorker] = None

        # доступность по профилю
        self.refresh_enabled(self._get_profile())

    # -------- public --------
    def is_enabled(self) -> bool:
        return bool(self.enabled_var.get())

    def set_mode(self, mode: str) -> None:
        self.mode_var.set((mode or BUFF_MODE_PROFILE).lower())
        if self._worker:
            self._worker.set_mode(self.mode_var.get())

    def refresh_enabled(self, profile) -> None:
        supports = bool(getattr(profile, "supports_buffing", lambda: False)())
        state = ("normal" if supports else "disabled")
        self.enabled_var.set(False if not supports else self.enabled_var.get())
        try:
            # чекбокс и селект
            for w in (self._frame,):
                pass
            # только меню нужно дизейблить явно
            self._mode_menu.configure(state=state)
        except Exception:
            pass
        self._status.config(text=("Готово" if supports else "Сервер не поддерживает баф"), fg=("gray" if supports else "red"))

    def run_once(self) -> bool:
        """
        Выполнить цикл бафа по текущему flow сервера.
        Возвращает True при успехе.
        """
        if not self._window_found():
            self._status.config(text="Окно не найдено", fg="red")
            return False
        w = self._ensure_worker()
        ok = w.run_once()
        self._status.config(text=("Баф выполнен" if ok else "Баф не выполнен"), fg=("green" if ok else "red"))
        return ok

    # -------- internals --------
    def _ensure_worker(self) -> BuffAfterRespawnWorker:
        if self._worker is None:
            def _status(text, ok=None):
                try:
                    self._status.config(text=text, fg=("green" if ok else ("red" if ok is False else "gray")))
                except Exception:
                    print(text)
            self._worker = BuffAfterRespawnWorker(
                controller=self._controller,
                server=self._get_server(),
                get_window=self._get_window,
                get_language=self._get_language,
                on_status=_status,
                click_threshold=0.87,
                debug=True,
            )
            self._worker.set_mode(self.mode_var.get())
        else:
            # обновим сервер и режим на случай смены
            self._worker.server = self._get_server()
            self._worker.set_mode(self.mode_var.get())
        return self._worker

    def _on_toggle(self):
        if self.enabled_var.get():
            self._status.config(text="Включено. Запустится после респавна.", fg="gray")
        else:
            self._status.config(text="Отключено", fg="gray")

    def _on_mode_change(self, mode: str):
        if self._worker:
            self._worker.set_mode(mode or BUFF_MODE_PROFILE)
