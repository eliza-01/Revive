# app/ui/window_probe.py
import tkinter as tk
from core.vision.capture import gdi

class WindowProbe:
    def __init__(self, root, on_found=None):
        self.root = root
        self.on_found = on_found
        self.window_info = None
        self.window_found = False
        self.window_titles = ["Lineage", "Lineage II", "L2MAD", "L2"]
        self.window_poll_interval_ms = 3000
        self._status_cb = None
        self._init_window_info_multi()
        if not self.window_found:
            print("[UI] Клиент не найден. Открой игру и нажми «Найти окно» — или подожди, авто-поиск сработает.")
        self._schedule_autofind()

    def attach_status_label(self, label_widget: tk.Label):
        def _cb(text: str):
            try:
                label_widget.config(text=text)
            except Exception:
                pass
        self._status_cb = _cb
        self._emit_status("[?] Поиск окна..." if not self.window_found else "[✓] Окно найдено")

    def current_window_info(self):
        return self.window_info

    def try_find_window_again(self):
        if self._init_window_info_multi():
            print("[UI] Окно найдено.")
        else:
            print("[UI] Пока нет. Убедись, что клиент запущен.")

    def _emit_status(self, text: str):
        if self._status_cb:
            self._status_cb(text)
        else:
            print(text)

    def _init_window_info(self, title: str = "Lineage", client: bool = True) -> bool:
        hwnd = gdi.find_window(title)
        print(f"[GDI] find_window '{title}': {hwnd}")
        if not hwnd:
            self.window_info = None
            return False
        info = gdi.get_window_info(hwnd, client=client)
        for k in ("x", "y", "width", "height"):
            if k not in info:
                print(f"[×] В window_info нет ключа '{k}'")
                self.window_info = None
                return False
        self.window_info = info
        if self.on_found:
            self.on_found(info)
        return True

    def _init_window_info_multi(self) -> bool:
        for t in self.window_titles:
            if self._init_window_info(title=t, client=True):
                self.window_found = True
                self._emit_status(f"[✓] Окно найдено: {t}")
                return True
        self.window_found = False
        print(f"[×] Окно клиента не найдено по заголовкам: {self.window_titles}")
        self._emit_status("[×] Окно не найдено")
        return False

    def _schedule_autofind(self):
        if not self.window_found:
            self.root.after(self.window_poll_interval_ms, self._autofind_tick)

    def _autofind_tick(self):
        if not self.window_found:
            found_now = self._init_window_info_multi()
            if found_now:
                print("[UI] Авто-поиск: окно найдено")
                self.window_found = True
                self._emit_status("[✓] Окно найдено")
            else:
                self._emit_status("[…] Окно не найдено — повтор через 3 сек")
                self._schedule_autofind()
