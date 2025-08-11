# main.py — точка входа в приложение

from core.updater import check_and_update, try_self_replace
from ui.launcher_ui import launch_gui
import threading
import sys

LOCAL_VERSION = "1.1.7"

# Флаг для остановки
stop_requested = False

def listen_for_kill():
    global stop_requested
    print("[INFO] Ожидание команды 'KILL' для завершения...")
    for line in sys.stdin:
        if line.strip().upper() == "KILL":
            stop_requested = True
            print("[STOP] Команда 'KILL' получена — завершение работы.")
            break

if __name__ == "__main__":
    # Запускаем слушатель в фоновом потоке
    kill_thread = threading.Thread(target=listen_for_kill, daemon=True)
    kill_thread.start()

    # Шаг 1: если запускаемся с флагом обновления — заменить .exe
    try_self_replace()

    # Шаг 2: проверяем наличие новой версии
    check_and_update(LOCAL_VERSION)

    # Шаг 3: запускаем GUI
    launch_gui(LOCAL_VERSION)
