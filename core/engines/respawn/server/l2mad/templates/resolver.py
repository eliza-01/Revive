# core/engines/respawn/server/boh/templates/resolver.py
# Жёсткий, предсказуемый резолвер для шаблонов respawn-движка.
# Поддерживает только известные файлы. Никаких плейсхолдеров.

import os
from typing import List, Optional

_LANG_FALLBACK = "rus"

# Разрешённые имена файлов в каталоге языка
_ALLOWED_FILES = {
    "to_village_button.png",
    "reborn_window.png",
    "accept_button.png",
    "decline_button.png",
    # добавишь сюда новые имена — они сразу начнут резолвиться
}

def _templates_root() -> str:
    # Абсолютный путь до каталога templates (этого файла)
    return os.path.abspath(os.path.dirname(__file__))

def _lang_dir(lang: str) -> str:
    lang = (lang or _LANG_FALLBACK).lower()
    return os.path.join(_templates_root(), lang)

def resolve(lang: str, *parts: str) -> Optional[str]:
    """
    Вернёт абсолютный путь к шаблону или None.
    Ожидаем вызовы вида:
      resolve("rus", "reborn_button.png")
      resolve("rus", "to_village_button.png")
    """
    # parts должны указывать на файл в корне языкового каталога
    if not parts or len(parts) != 1:
        return None
    filename = parts[0]
    if filename not in _ALLOWED_FILES:
        return None

    path = os.path.join(_lang_dir(lang), filename)
    return path if os.path.isfile(path) else None

def exists(lang: str, *parts: str) -> bool:
    return resolve(lang, *parts) is not None

def listdir(lang: str, *parts: str) -> List[str]:
    # Возвращаем только разрешённые файлы, которые реально существуют
    base = _lang_dir(lang)
    out: List[str] = []
    for name in sorted(_ALLOWED_FILES):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            out.append(name)
    return out
