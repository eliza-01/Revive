# main.py
import os
import sys

from app import launch_gui

def _base_dir():
    # Путь рядом с исполняемым файлом при PyInstaller, иначе — рядом с этим скриптом
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))

def get_local_version() -> str:
    # 1) Переменная окружения имеет приоритет
    env_ver = os.getenv("REVIVE_VERSION")
    if env_ver:
        return env_ver.strip()

    # 2) Файл VERSION в корне проекта
    try:
        with open(os.path.join(_base_dir(), "VERSION"), "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass

    # 3) Запасное значение
    return "0.0.0"

if __name__ == "__main__":
    launch_gui(get_local_version())
