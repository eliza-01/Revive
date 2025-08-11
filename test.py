# test_hp_monitor.py
import time
from core.features.player_state import PlayerStateMonitor
from core.vision.win32.gdi_backend import find_window, get_window_info

def get_window():
    hwnd = find_window("Lineage")
    return get_window_info(hwnd, client=True) if hwnd else None

if __name__ == "__main__":
    monitor = PlayerStateMonitor(
        server="l2mad",      # твой сервер
        get_window=get_window,
        on_update=None,      # можем не использовать
        poll_interval=1,
        debug=True           # включаем вывод HP в консоль
    )
    monitor.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
