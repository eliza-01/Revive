# core/arduino/send_safe.py
from __future__ import annotations

import logging
from core.arduino.send_command import send_command
from core.logging import console

def send_click_left(ser, debug: bool = False) -> bool:
    try:
        if ser is None or not getattr(ser, "is_open", False):
            msg = "[arduino] port not open"
            if debug:
                logging.info(msg)
            console.log(msg)
            return False

        send_command(ser, "l")
        port = getattr(ser, "port", "?")
        if debug:
            logging.info("[arduino] click left OK on %s", port)
        console.log(f"[arduino] click left OK on {port}")
        return True

    except Exception as e:
        if debug:
            logging.info("[arduino] send failed: %s", e)
        console.log(f"[arduino] send failed: {e}")
        return False
