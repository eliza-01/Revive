# core/arduino/connection_test.py
def run_test_command(controller, status_label=None):
    try:
        controller.send("ping")
        resp = controller.read()
        ok = (resp == "pong")
        msg = "Связь OK" if ok else "Нет ответа"
        if status_label is not None:
            try:
                status_label.config(text=msg, fg=("green" if ok else "red"))
            except Exception:
                pass
        print(f"[test] {msg}")
        return ok
    except Exception as e:
        if status_label is not None:
            try:
                status_label.config(text=f"Ошибка: {e}", fg="red")
            except Exception:
                pass
        print(f"[test] Ошибка: {e}")
        return False
