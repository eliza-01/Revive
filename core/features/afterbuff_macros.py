from __future__ import annotations
import time
from typing import Iterable

ALLOWED_KEYS = tuple("0123456789-=")

class AfterBuffMacroRunner:
    def __init__(self, controller, get_sequence, get_delay_ms):
        self.controller = controller
        self._get_sequence = get_sequence
        self._get_delay_ms = get_delay_ms

    def run_once(self) -> bool:
        try:
            seq: Iterable[str] = list(self._get_sequence() or [])
            delay_ms = int(self._get_delay_ms() or 0)
            delay_s = max(0.0, delay_ms / 1000.0)

            for k in seq:
                ch = str(k).strip()
                if len(ch) != 1 or ch not in ALLOWED_KEYS:
                    continue
                self.controller.send(ch)   # прошивка: одиночный символ
                time.sleep(delay_s)
            return True
        except Exception as e:
            print(f"[macros] error: {e}")
            return False
