# hotkey.py
# pip install pynput
import time
import threading
import sys

try:
    from pynput import keyboard
except Exception as e:
    print(f"[hotkey] pynput import error: {e}", flush=True)
    sys.exit(1)

stop_evt = threading.Event()

def on_ctrl_r():
    ts = time.strftime("%H:%M:%S")
    print(f"[hotkey] CTRL+R triggered @ {ts}", flush=True)

def on_esc():
    print("[hotkey] ESC pressed -> exiting", flush=True)
    stop_evt.set()

def main():
    print("[hotkey] waiting for global hotkey: Ctrl+R (Esc to quit)", flush=True)
    hk = keyboard.GlobalHotKeys({
        '<ctrl>+r': on_ctrl_r,
        '<esc>': on_esc,
    })
    hk.start()
    try:
        # держим главный поток живым
        while not stop_evt.is_set():
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("[hotkey] KeyboardInterrupt -> exiting", flush=True)
    finally:
        try:
            hk.stop()
            hk.join(1.0)
        except Exception:
            pass
        print("[hotkey] stopped.", flush=True)

if __name__ == "__main__":
    main()
