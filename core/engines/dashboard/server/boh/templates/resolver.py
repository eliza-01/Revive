# core/engines/dashboard/server/boh/templates/resolver.py
# Резолвер для шаблонов dashboard-движка.
# Поддерживает плейсхолдер "<lang>", алиасы языков и вложенные подпапки.
# Разрешает только реально существующие файлы под eng/, rus/ и common/.

from __future__ import annotations
import os
from typing import List, Optional, Tuple

_LANG_FALLBACK = "rus"
_LANG_ALIASES = {
    "ru": "rus", "rus": "rus", "russian": "rus",
    "en": "eng", "eng": "eng", "english": "eng",
}

# Для починки опечатки "сommon" (кириллическая 'с')
_CYR_TO_LAT = {ord("с"): "c", ord("С"): "C"}

def _templates_root() -> str:
    # .../core/engines/dashboard/server/boh/templates
    return os.path.abspath(os.path.dirname(__file__))

def _norm_lang(lang: str) -> str:
    lang = (lang or _LANG_FALLBACK).lower().strip()
    return _LANG_ALIASES.get(lang, _LANG_FALLBACK)

def _lang_dir(lang: str) -> str:
    return os.path.join(_templates_root(), _norm_lang(lang))

def _common_dir() -> str:
    return os.path.join(_templates_root(), "common")

def _is_common_token(token: str) -> bool:
    return token.translate(_CYR_TO_LAT).lower().strip() == "common"

def _scan_dir(base: str) -> set[str]:
    out: set[str] = set()
    if not os.path.isdir(base):
        return out
    for root, _dirs, files in os.walk(base):
        for fn in files:
            if not fn.lower().endswith(".png"):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, base).replace("\\", "/")
            out.add(rel)
    return out

# --- Белые списки формируются автоматически по содержимому eng/, rus/ и common/ ---
_ALLOWED_REL_LANG: set[str] = set()     # относительные пути, встречающиеся в eng/ или rus/
for _L in ("eng", "rus"):
    _ALLOWED_REL_LANG |= _scan_dir(os.path.join(_templates_root(), _L))

_ALLOWED_REL_COMMON: set[str] = _scan_dir(_common_dir())

def _safe_join(base_dir: str, *parts: str) -> Optional[str]:
    # Собираем путь под base_dir, защищаемся от traversal
    joined = os.path.join(base_dir, *parts)
    normd  = os.path.abspath(joined)
    base   = os.path.abspath(base_dir)
    if not normd.startswith(base + os.sep) and normd != base:
        return None
    return normd

def _try_langs(rel_parts: Tuple[str, ...], lang: str) -> Optional[str]:
    """
    Порядок попыток: lang -> rus -> eng
    """
    rel_norm = "/".join(rel_parts)
    # сначала проверяем, что такой относительный путь вообще встречался в eng/ или rus/
    if rel_norm not in _ALLOWED_REL_LANG:
        return None

    for L in (_norm_lang(lang), "rus", "eng"):
        base = _lang_dir(L)
        p = _safe_join(base, *rel_parts)
        if p and os.path.isfile(p):
            return p
    return None

def _try_common(rel_parts: Tuple[str, ...]) -> Optional[str]:
    rel_norm = "/".join(rel_parts)
    if rel_norm not in _ALLOWED_REL_COMMON:
        return None
    base = _common_dir()
    p = _safe_join(base, *rel_parts)
    if p and os.path.isfile(p):
        return p
    return None

def resolve(lang: str, *parts: str) -> Optional[str]:
    """
    Примеры:
      resolve("rus", "<lang>", "main", "dashboard_init.png")
      resolve("eng", "<lang>", "buffer", "icons", "buffs", "mental_shield.png")
      resolve("eng", "common", "buffer", "icons", "buffs", "mental_shield.png")  # явный common
    """
    if not parts:
        return None

    # поддерживаем как "<lang>", так и уже нормализованный язык первым сегментом
    # и явный (или опечаточный) "common"
    head = parts[0]
    if head in ("<lang>", "lang"):
        rel_parts = tuple(parts[1:])
        # 1) пробуем языковые каталоги
        p = _try_langs(rel_parts, lang)
        if p:
            return p
        # 2) фолбэк в common
        return _try_common(rel_parts)

    head_norm = head.lower()
    if head_norm in ("eng", "rus"):
        # Язык указан явно в пути
        lang = head_norm
        rel_parts = tuple(parts[1:])
        p = _try_langs(rel_parts, lang)
        if p:
            return p
        # фолбэк в common
        return _try_common(rel_parts)

    if _is_common_token(head):
        # Явный common (и/или "сommon" с кириллической 'с')
        rel_parts = tuple(parts[1:])
        return _try_common(rel_parts)

    # Иначе считаем, что первый сегмент — это подпапка,
    # и требуется "<lang>" в TEMPLATES (т.е. пытаемся как языковой путь)
    rel_parts = tuple(parts)
    p = _try_langs(rel_parts, lang)
    if p:
        return p
    return _try_common(rel_parts)

def exists(lang: str, *parts: str) -> bool:
    return resolve(lang, *parts) is not None

def listdir(lang: str, *parts: str) -> List[str]:
    """
    Возвращает список разрешённых файлов, реально существующих:
      - если parts начинается с common/ — из common
      - иначе: из указанного языка (с учётом наличия)
    """
    out: List[str] = []
    if parts and _is_common_token(parts[0]):
        base = _common_dir()
        rel_prefix = "/".join(parts[1:]).replace("\\", "/")
        for rel in sorted(_ALLOWED_REL_COMMON):
            if not rel_prefix or rel.startswith(rel_prefix):
                p = os.path.join(base, rel)
                if os.path.isfile(p):
                    out.append(rel)
        return out

    base = _lang_dir(_norm_lang(lang))
    rel_prefix = "/".join(parts[1:] if (parts and parts[0] in ("<lang>", "lang")) else parts).replace("\\", "/")
    for rel in sorted(_ALLOWED_REL_LANG):
        if not rel_prefix or rel.startswith(rel_prefix):
            p = os.path.join(base, rel)
            if os.path.isfile(p):
                out.append(rel)
    return out
