# core/arduino/send_safe.py
import logging
from core.arduino.send_command import send_command

def send_click_left(ser, debug=False) -> bool:
    try:
        if ser is None or not getattr(ser, "is_open", False):
            if debug: logging.info("[arduino] port not open")
            return False
        send_command(ser, "l")
        if debug: logging.info("[arduino] click left OK on %s", getattr(ser, "port", "?"))
        return True
    except Exception as e:
        if debug: logging.info("[arduino] send failed: %s", e)
        return False
