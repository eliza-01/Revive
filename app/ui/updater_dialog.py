# app/ui/updater_dialog.py
import threading
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import scrolledtext

from core.updater import (
    get_remote_version,
    get_update_changelog,
    is_newer_version,
    launch_downloaded_exe_and_exit,
    download_new_exe,
)

def run_update_check(local_version, version_status_label, root, app):
    def check():
        try:
            remote_version = get_remote_version()
            def apply_result():
                nonlocal remote_version
                if getattr(app, "update_window_ref", None) and app.update_window_ref.winfo_exists():
                    print("[!] Окно обновления уже открыто, пропуск")
                    return
                if is_newer_version(remote_version, local_version):
                    version_status_label.config(text=f"Доступно обновление: {remote_version}", fg="orange")
                    app.update_window_ref = show_update_window(root, remote_version, app)
                else:
                    version_status_label.config(text=f"Установлена последняя версия: {local_version}", fg="green")
            root.after(0, apply_result)
        except Exception as e:
            def apply_error():
                version_status_label.config(text="Сбой проверки актуальности версии", fg="red")
            root.after(0, apply_error)
            print("[Ошибка проверки версии]", e)
    threading.Thread(target=check, daemon=True).start()

def show_update_window(root, remote_version, app):
    update_win = tk.Toplevel(root)
    app.update_window_ref = update_win

    update_win.title(f"Доступно обновление: {remote_version}")
    update_win.geometry("490x400")
    update_win.resizable(True, True)

    tk.Label(update_win, text=f"Доступна новая версия: {remote_version}", font=("Arial", 12)).pack(pady=10)

    try:
        changelog = get_update_changelog()
    except Exception:
        changelog = "Не удалось загрузить список изменений."

    scroll_text = scrolledtext.ScrolledText(update_win, wrap="word", font=("Arial", 10), height=10)
    scroll_text.insert(tk.END, changelog)
    scroll_text.configure(state="disabled")
    scroll_text.pack(expand=True, fill="both", padx=10, pady=(0, 10))

    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(update_win, variable=progress_var, maximum=100)
    progress_bar.pack(fill="x", padx=20, pady=(5, 0))

    progress_label = tk.Label(update_win, text="Ожидание начала загрузки...", font=("Arial", 9))
    progress_label.pack()

    def start_update():
        try:
            app.respawn.stop()
        except Exception:
            pass
        try:
            app.controller.close()
        except Exception:
            pass

        def download():
            try:
                def progress_callback(percent):
                    progress_var.set(percent)
                    progress_label.config(text=f"Загрузка: {int(percent)}%")
                    progress_bar.update_idletasks()

                exe_name = download_new_exe(remote_version, progress_callback)
                progress_label.config(text="✅ Загрузка завершена.")
                update_win.after(500, lambda: [update_win.destroy(), launch_downloaded_exe_and_exit(exe_name)])
            except Exception as e:
                progress_label.config(text=f"Ошибка загрузки: {e}")

        threading.Thread(target=download, daemon=True).start()

    button_frame = tk.Frame(update_win)
    button_frame.pack(pady=10)

    tk.Button(button_frame, text="Скачать и установить", command=start_update).pack(side="left", padx=10)
    tk.Button(button_frame, text="Отмена", command=update_win.destroy).pack(side="right", padx=10)

    return update_win
