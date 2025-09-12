# core/engines/dashboard/server/boh/templates/resolver.py
# Резолвер для шаблонов dashboard-движка.
# Поддерживает плейсхолдер "<lang>", алиасы языков и вложенные подпапки.
# Разрешает только реально существующие файлы под eng/ и rus/.

from __future__ import annotations
import os
from typing import List, Optional

_LANG_FALLBACK = "rus"
_LANG_ALIASES = {
    "ru": "rus", "rus": "rus", "russian": "rus",
    "en": "eng", "eng": "eng", "english": "eng",
}

def _templates_root() -> str:
    # .../core/engines/dashboard/server/boh/templates
    return os.path.abspath(os.path.dirname(__file__))

def _norm_lang(lang: str) -> str:
    lang = (lang or _LANG_FALLBACK).lower().strip()
    return _LANG_ALIASES.get(lang, _LANG_FALLBACK)

def _lang_dir(lang: str) -> str:
    return os.path.join(_templates_root(), _norm_lang(lang))

# --- Белый список формируется автоматически по содержимому eng/ и rus/ ---
_ALLOWED_REL: set[str] = set()
for _L in ("eng", "rus"):
    base = os.path.join(_templates_root(), _L)
    if not os.path.isdir(base):
        continue
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if not fn.lower().endswith(".png"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, base).replace("\\", "/")
            _ALLOWED_REL.add(rel)

def _safe_join_lang(lang_dir: str, *parts: str) -> Optional[str]:
    # Собираем путь под lang_dir, защищаемся от traversal
    joined = os.path.join(lang_dir, *parts)
    normd  = os.path.abspath(joined)
    if not normd.startswith(os.path.abspath(lang_dir) + os.sep):
        return None
    return normd

def resolve(lang: str, *parts: str) -> Optional[str]:
    """
    Примеры:
      resolve("rus", "<lang>", "main", "dashboard_init.png")
      resolve("eng", "<lang>", "buffer", "dashboard_buffer_init.png")
    """
    if not parts:
        return None

    # поддерживаем как "<lang>", так и уже нормализованный язык первым сегментом
    if parts[0] in ("<lang>", "lang"):
        rel_parts = parts[1:]
    elif parts[0].lower() in ("eng", "rus"):
        rel_parts = parts[1:]
        lang = parts[0].lower()
    else:
        # считаем, что первый сегмент — это подпапка (требуется "<lang>" в TEMPLATES)
        rel_parts = parts

    # белый список сравниваем по пути относительно lang-директории в POSIX-формате
    rel_norm = "/".join(rel_parts)
    if rel_norm not in _ALLOWED_REL:
        return None

    base = _lang_dir(lang)
    p = _safe_join_lang(base, *rel_parts)
    if not p or not os.path.isfile(p):
        return None
    return p

def exists(lang: str, *parts: str) -> bool:
    return resolve(lang, *parts) is not None

def listdir(lang: str, *parts: str) -> List[str]:
    # Возвращаем список разрешённых файлов, реально существующих для языка
    base = _lang_dir(lang)
    out: List[str] = []
    for rel in sorted(_ALLOWED_REL):
        p = os.path.join(base, rel)
        if os.path.isfile(p):
            out.append(rel)
    return out
