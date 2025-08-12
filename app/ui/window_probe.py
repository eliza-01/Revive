# app/ui/window_probe.py
import tkinter as tk
import time
from typing import Callable, Optional, Dict, List

from core.vision.capture.gdi import find_window, get_window_info

class WindowProbe:
    """
    Автопоиск окна Lineage. Периодически пытается найти окно по списку заголовков.
    Публичный интерфейс:
      - attach_status(label: tk.Label) -> None     # привязать виджет статуса
      - try_find_window_again() -> None            # форс-поиск сейчас
      - current_window_info() -> Optional[dict]    # вернуть кеш window_info
      - window_found (bool)                        # флаг «окно найдено»
    """

    def __init__(self, root: tk.Tk, on_found: Callable[[Dict], None], titles: Optional[List[str]] = None, poll_ms: int = 3000):
        self.root = root
        self.on_found_cb = on_found
        self.window_titles = titles or ["Lineage", "Lineage II", "L2MAD", "L2"]
        self.window_poll_interval_ms = int(poll_ms)

        self.window_info: Optional[Dict] = None
        self.window_found: bool = False

        self._status_label: Optional[tk.Label] = None

        # первичный запуск авто-поиска
        self._init_window_info_multi()
        if not self.window_found:
            self._emit("[UI] Клиент не найден. Открой игру и нажми «Найти окно» — или подожди, авто-поиск сработает.")
        self._schedule_autofind()

    # ---------- API ----------
    def attach_status(self, label_widget: tk.Label) -> None:
        """Привязать Label для показа состояния поиска окна."""
        self._status_label = label_widget
        self._render_status("[✓] Окно найдено" if self.window_found else "[?] Поиск окна...")

    def try_find_window_again(self) -> None:
        """Ручной запуск поиска окна."""
        if self._init_window_info_multi():
            self._emit("[UI] Окно найдено.")
            self._render_status("[✓] Окно найдено")
        else:
            self._emit("[UI] Пока нет. Убедись, что клиент запущен.")
            self._render_status("[×] Окно не найдено")

    def current_window_info(self) -> Optional[Dict]:
        return self.window_info

    # ---------- internals ----------
    def _emit(self, text: str) -> None:
        try:
            print(text)
        except Exception:
            pass

    def _render_status(self, text: str) -> None:
        try:
            if self._status_label is not None:
                self._status_label.config(text=text)
        except Exception:
            pass

    def _schedule_autofind(self) -> None:
        if not self.window_found:
            self.root.after(self.window_poll_interval_ms, self._autofind_tick)

    def _autofind_tick(self) -> None:
        if self.window_found:
            return
        found_now = self._init_window_info_multi()
        if found_now:
            self._emit("[UI] Авто-поиск: окно найдено")
            self._render_status("[✓] Окно найдено")
        else:
            self._render_status("[…] Окно не найдено — повтор через 3 сек")
            self._schedule_autofind()

    def _init_window_info_multi(self) -> bool:
        for t in self.window_titles:
            if self._init_window_info(title=t, client=True):
                self.window_found = True
                self._render_status(f"[✓] Окно найдено: {t}")
                try:
                    if callable(self.on_found_cb):
                        self.on_found_cb(self.window_info)
                except Exception:
                    pass
                return True
        self.window_found = False
        self._emit(f"[×] Окно клиента не найдено по заголовкам: {self.window_titles}")
        self._render_status("[×] Окно не найдено")
        return False

    def _init_window_info(self, title: str = "Lineage", client: bool = True) -> bool:
        hwnd = find_window(title)
        self._emit(f"[GDI] find_window '{title}': {hwnd}")
        if not hwnd:
            self.window_info = None
            return False
        info = get_window_info(hwnd, client=client)
        for k in ("x", "y", "width", "height"):
            if k not in info:
                self._emit(f"[×] В window_info нет ключа '{k}'")
                self.window_info = None
                return False
        self.window_info = info
        return True