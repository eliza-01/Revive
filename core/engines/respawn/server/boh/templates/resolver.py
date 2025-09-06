# core/engines/respawn/server/boh/templates/resolver.py
# Жёсткий, предсказуемый резолвер для шаблонов respawn-движка.
# Теперь поддерживает плейсхолдер "<lang>", алиасы языков и языковые фолбэки.

import os
from typing import List, Optional

_LANG_FALLBACK = "rus"

# Алиасы языков на всякий случай
_LANG_ALIASES = {
    "ru": "rus",
    "rus": "rus",
    "russian": "rus",
    "en": "eng",
    "eng": "eng",
    "english": "eng",
}

# Разрешённые имена файлов в каталоге языка
_ALLOWED_FILES = {
    "to_village_button.png",
    "reborn_window.png",
    "accept_button.png",
    "decline_button.png",
    # добавишь сюда новые имена — они сразу начнут резолвиться
}

def _templates_root() -> str:
    return os.path.abspath(os.path.dirname(__file__))

def _norm_lang(lang: str) -> str:
    lang = (lang or _LANG_FALLBACK).lower().strip()
    return _LANG_ALIASES.get(lang, _LANG_FALLBACK)

def _lang_dir(lang: str) -> str:
    return os.path.join(_templates_root(), _norm_lang(lang))

def _try_path(lang: str, filename: str) -> Optional[str]:
    if filename not in _ALLOWED_FILES:
        return None
    p = os.path.join(_lang_dir(lang), filename)
    return p if os.path.isfile(p) else None

def resolve(lang: str, *parts: str) -> Optional[str]:
    """
    Поддерживаем вызовы вида:
      resolve("rus", "reborn_window.png")                # 1 сегмент
      resolve("rus", "<lang>", "reborn_window.png")      # 2 сегмента с плейсхолдером
    Выполняем фолбэк по языкам: lang → rus → eng.
    """
    # вытащим имя файла
    filename: Optional[str] = None
    if not parts:
        return None
    if len(parts) == 1:
        filename = parts[0]
    elif len(parts) == 2 and parts[0] in ("<lang>", "lang"):
        filename = parts[1]
    else:
        # не поддерживаем вложенные подпапки и лишние сегменты
        return None

    if filename not in _ALLOWED_FILES:
        return None

    langs_to_try = []
    prim = _norm_lang(lang)
    langs_to_try.append(prim)
    if "rus" not in langs_to_try:
        langs_to_try.append("rus")
    if "eng" not in langs_to_try:
        langs_to_try.append("eng")

    for L in langs_to_try:
        p = _try_path(L, filename)
        if p:
            return p
    return None

def exists(lang: str, *parts: str) -> bool:
    return resolve(lang, *parts) is not None

def listdir(lang: str, *parts: str) -> List[str]:
    # Возвращаем только разрешённые файлы, которые реально существуют в нормализованном языке
    base = _lang_dir(lang)
    out: List[str] = []
    for name in sorted(_ALLOWED_FILES):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            out.append(name)
    return out
