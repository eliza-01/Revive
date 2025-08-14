# core/features/afterbuff_macros.py
from __future__ import annotations
import time
from typing import Callable, Iterable, List

class AfterBuffMacroRunner:
    """
    Последовательно отправляет выбранные клавиши на Arduino.
    Задержка между нажатиями — уже в СЕКУНДАХ (как в UI).
    """
    def __init__(
            self,
            controller,
            get_sequence: Callable[[], Iterable[str]],
            get_delay_s: Callable[[], float],
    ):
        self.controller = controller
        self._get_sequence = get_sequence
        self._get_delay_s = get_delay_s

    def run_once(self) -> bool:
        seq: List[str] = list(self._get_sequence() or [])
        try:
            delay_s = float(self._get_delay_s() or 0.0)
        except Exception:
            delay_s = 0.0

        if not seq:
            print("[macros] run: empty sequence")
            return False

        print(f"[macros] run: {seq}, delay={delay_s:.3f} s")

        sent = 0
        for idx, key in enumerate(seq, start=1):
            if not key:
                continue
            ch = str(key)[0]
            self.controller.send(ch)
            sent += 1
            print(f"[macros] sent {idx}/{len(seq)} → '{ch}'")
            if idx < len(seq) and delay_s > 0:
                time.sleep(delay_s)

        print(f"[macros] done, sent={sent}")
        return sent > 0
