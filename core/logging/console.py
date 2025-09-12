# core/logging/console.py
from __future__ import annotations
from typing import Optional
import json
import os
from core.state.pool import pool_get

# console.log("Сработал удар по мобу X123")
# console.log(f"удар по мобу {mob}")

# console.hud(state, "macros.started")  # по ключу из словаря
# console.hud(state, "Текст {name}", name="значение переменной")  # произвольный текст с переменной

_LANG_FALLBACK = "ru"
_LOADED = {"ru": {}, "en": {}}


# --- Подгрузка языковых словарей один раз ---
def _load_dict(lang: str):
    if _LOADED[lang]:
        return
    path = os.path.join(os.path.dirname(__file__), f"hud_{lang}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            _LOADED[lang] = json.load(f)
    except Exception as e:
        print(f"[console.hud] failed to load hud_{lang}.json: {e}")
        _LOADED[lang] = {}


def hud(state: dict, key_or_text: Optional[str], **kwargs):
    """
    Отправка в HUD.
    - Если key_or_text — ключ из словаря → подставляем язык и .format(**kwargs)
    - Если key_or_text — обычный текст (и нет ключа в словарях) → шлём как есть
    """
    if not key_or_text:
        return

    lang = pool_get(state, "config.app_language", _LANG_FALLBACK).lower().strip()
    if lang not in ("ru", "en"):
        lang = _LANG_FALLBACK

    _load_dict(lang)
    _load_dict(_LANG_FALLBACK)

    text = _LOADED.get(lang, {}).get(key_or_text)
    if not text:
        text = _LOADED.get(_LANG_FALLBACK, {}).get(key_or_text)
    if not text:
        text = key_or_text

    try:
        text = text.format(**kwargs)
    except Exception:
        pass  # если что-то не так с format — оставим как есть

    print(text)

    # HUD push (если есть)
    try:
        from app.launcher.infra.ui_bridge import UIBridge
        if hasattr(UIBridge, "hud_push"):
            UIBridge.hud_push(UIBridge, text)  # вызов статически, без экземпляра
    except Exception:
        pass


def log(text: str):
    print(text)