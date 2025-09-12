# core/arduino/serial_port.py
import time
import serial
import serial.tools.list_ports
from core.logging import console

def find_arduino_port(vid_pid_hint=None):
    """
    Возвращает COM-порт, к которому подключен Arduino.
    Если передан vid_pid_hint=(VID, PID) — фильтруем точнее.
    """
    for port in serial.tools.list_ports.comports():
        if vid_pid_hint and (port.vid, port.pid) == tuple(vid_pid_hint):
            return port.device
        desc = (port.description or "") + " " + (port.manufacturer or "")
        if "Arduino" in desc or "USB" in desc:
            return port.device
    return None

def init_serial(port=None, baudrate=9600, timeout=1):
    """
    Возвращает открытый serial.Serial объект.
    Если port не указан — автоопределяем.
    """
    if port is None:
        port = find_arduino_port()
    if port is None:
        raise RuntimeError("Arduino COM-порт не найден.")

    try:
        ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        console.log(f"[✓] Arduino найден на порту: {port}")
        time.sleep(2)  # подождать инициализацию MCU после открытия порта
        return ser
    except Exception as e:
        raise RuntimeError(f"[×] Ошибка открытия порта {port}: {e}")
