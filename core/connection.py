# core/connection.py
import time

class ReviveController:
    def __init__(self):
        self._last_cmd = None
        self._closed = False

    def send(self, cmd: str):
        if self._closed:
            raise RuntimeError("Controller is closed")
        self._last_cmd = cmd
        print(f"[controller] send: {cmd}")

    def read(self, timeout: float = 0.2):
        if self._closed:
            return None
        time.sleep(min(max(timeout, 0.0), 0.5))
        if self._last_cmd == "ping":
            return "pong"
        return "ok"

    def close(self):
        self._closed = True
        print("[controller] closed")
