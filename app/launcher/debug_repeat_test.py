from time import sleep

from app.launcher.wiring import build_container
import webview

# заглушка окна (если нужно)
class DummyWindow:
    def evaluate_js(self, js): pass

window = DummyWindow()

container = build_container(window=window, local_version="0.0.0")
sys_state = container["sections"][0].sys_state
macros_repeat_service = sys_state["_services"]["macros_repeat"]

# ручная настройка
sys_state["macros_rows"] = [{"key": "4", "cast_s": 0, "repeat_s": 3}]
sys_state["macros_enabled"] = True
sys_state["macros_repeat_enabled"] = True

# запускаем сервис
macros_repeat_service.start()

# ждём повторы
sleep(10)
