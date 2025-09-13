# tools/rectest.py
# pip install pynput
from pynput import mouse
import time

MOVE_INTERVAL = 0.2  # 200 мс
_last_pos = None
_ctrl = mouse.Controller()

def _poll_moves():
    global _last_pos
    while True:
        pos = _ctrl.position
        if pos != _last_pos:
            print(f"MOVE x={pos[0]} y={pos[1]}", flush=True)
            _last_pos = pos
        time.sleep(MOVE_INTERVAL)

def _on_click(x, y, button, pressed):
    state = "DOWN" if pressed else "UP"
    btn = getattr(button, "name", str(button))
    print(f"CLICK {state} {btn} x={x} y={y}", flush=True)

def _on_scroll(x, y, dx, dy):
    print(f"WHEEL dx={dx} dy={dy} x={x} y={y}", flush=True)

if __name__ == "__main__":
    listener = mouse.Listener(on_click=_on_click, on_scroll=_on_scroll)
    listener.start()
    try:
        _poll_moves()  # основная нить опрашивает курсор раз в 200мс
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        listener.join()
