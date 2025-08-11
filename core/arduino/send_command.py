# core/arduino/send_command.py
def send_command(ser, command: str):
    """
    Пишет строку в Serial и добавляет '\n' при необходимости.
    """
    if ser is None:
        print("[×] Порт не инициализирован (ser=None)")
        return
    if not getattr(ser, "is_open", False):
        print(f"[×] Порт {getattr(ser, 'port', '?')} закрыт.")
        return
    try:
        if not command.endswith("\n"):
            command += "\n"
        ser.write(command.encode("utf-8"))
        print(f"[>>] {command.strip()}")
    except Exception as e:
        print(f"[×] Ошибка при отправке: {e}")
