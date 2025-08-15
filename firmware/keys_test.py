# test_arduino_driver.py
# Требует: pip install pyserial
import argparse
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except Exception:
    print("Установите pyserial: pip install pyserial")
    sys.exit(1)

def autodetect_port() -> str | None:
    for p in list_ports.comports():
        desc = f"{p.manufacturer} {p.description} {p.hwid}".lower()
        if any(k in desc for k in ["arduino", "ch340", "wch", "usb serial", "sparkfun", "leonardo", "micro"]):
            return p.device
    return None

def send_line(ser: serial.Serial, cmd: str) -> None:
    ser.write((cmd.strip() + "\n").encode("utf-8"))
    ser.flush()

def read_line(ser: serial.Serial, timeout: float = 2.0) -> str | None:
    end = time.time() + timeout
    buf = bytearray()
    while time.time() < end:
        b = ser.read(1)
        if b:
            if b in (b"\n", b"\r"):
                if buf:
                    break
                else:
                    continue
            buf.extend(b)
        else:
            time.sleep(0.01)
    return buf.decode("utf-8", errors="ignore").strip() if buf else None

def main():
    ap = argparse.ArgumentParser(description="Test Arduino serial commands: ping/pageup/pagedown")
    ap.add_argument("--port", help="COM-порт, например COM5 или /dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200, help="baudrate (по умолчанию 115200)")
    ap.add_argument("--no-auto", action="store_true", help="не пытаться автоопределять порт")
    ap.add_argument("--delay", type=float, default=0.3, help="задержка между командами, сек")
    ap.add_argument("--pong-timeout", type=float, default=2.0, help="таймаут ожидания pong, сек")
    args = ap.parse_args()

    port = args.port or (None if args.no_auto else autodetect_port())
    if not port:
        print("Не указан порт и не удалось автоопределить. Пример: --port COM5")
        sys.exit(2)

    print(f"[i] Открываю порт: {port} @ {args.baud}")
    try:
        with serial.Serial(port, args.baud, timeout=0.1) as ser:
            # Многие Arduino перезагружаются при открытии порта
            time.sleep(1.5)
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            # 1) ping → ждём pong
            print("[>] ping")
            send_line(ser, "ping")
            resp = read_line(ser, timeout=args.pong_timeout)
            ok = (resp == "pong")
            print(f"[<] {resp if resp is not None else '(timeout)'}")
            print(f"[=] PING: {'OK' if ok else 'FAIL'}")

            # 2) pageup
            time.sleep(args.delay)
            print("[>] pageup  (проверьте, активное окно должно пролистаться вверх)")
            send_line(ser, "pageup")

            # 3) pagedown
            time.sleep(args.delay)
            print("[>] pagedown (проверьте, активное окно должно пролистаться вниз)")
            send_line(ser, "pagedown")

            # опциональная «release» если прошивка это поддерживает
            time.sleep(args.delay)
            print("[>] release (если реализовано в прошивке)")
            send_line(ser, "release")

            print("[✓] Тест завершён.")
    except serial.SerialException as e:
        print(f"[!] Serial error: {e}")
        sys.exit(3)

if __name__ == "__main__":
    main()
