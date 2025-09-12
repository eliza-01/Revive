# core/arduino/send_command.py
from __future__ import annotations

from core.logging import console

def send_command(ser, command: str):
    """
    Пишет строку в Serial и добавляет '\n' при необходимости.
    """
    if ser is None:
        console.log("[×] Порт не инициализирован (ser=None)")
        return
    if not getattr(ser, "is_open", False):
        console.log(f"[×] Порт {getattr(ser, 'port', '?')} закрыт.")
        return
    try:
        if not command.endswith("\n"):
            command += "\n"
        ser.write(command.encode("utf-8"))
        console.log(f"[>>] {command.strip()}")
    except Exception as e:
        console.log(f"[×] Ошибка при отправке: {e}")
