# core/engines/ui_guard/server/boh_x500/templates/resolver.py
from __future__ import annotations
import os
from typing import Optional

_BASE = os.path.dirname(__file__)  # .../server/boh/templates

def resolve(lang: str, *parts: str) -> Optional[str]:
    """
    Сборщик пути к шаблону. Поддерживает маркер "<lang>".
    """
    lang = (lang or "rus").lower()
    segs = []
    for p in parts:
        if p == "<lang>":
            segs.append(lang)
        else:
            segs.append(p)
    path = os.path.join(_BASE, *segs)
    return path if os.path.exists(path) else None
