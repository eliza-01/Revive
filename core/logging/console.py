# core/logging/console.py
from __future__ import annotations
from typing import Optional, Callable, Dict
import json
import os

# from core.logging import console

# Публичный API:
#   console.bind(hud_push=callable)                 # callable(status:str, text:str) -> None
#   console.set_language("ru" | "en")               # обязателен до первого hud()
#   console.log("в stdout")
#   console.hud("ok",  "macros.started", name="X")  # ключ из словаря
#   console.hud("err", "Ошибка {code}", code=13)    # прямой текст

_SUPPORTED_LANGS = {"ru", "en"}
_ALLOWED_STATUS  = {"err", "succ", "ok"}

_DICT_CACHE: Dict[str, Dict[str, str]] = {}

_HUD_PUSH: Optional[Callable[[str, str], None]] = None
_LANG: Optional[str] = None  # текущий язык; без него hud() не работает

def bind(*, hud_push: Callable[[str, str], None]) -> None:
    """Привязка функции отправки в HUD (обязательна до первого hud())."""
    if not callable(hud_push):
        raise TypeError("console.bind: hud_push must be callable(status:str, text:str) -> None")
    global _HUD_PUSH
    _HUD_PUSH = hud_push

def set_language(lang: str) -> None:
    """Установить язык ('ru'|'en'). Никаких автоподстановок."""
    if lang not in _SUPPORTED_LANGS:
        raise ValueError(f"console.set_language: unsupported language '{lang}'")
    global _LANG
    _LANG = lang

def _load_lang_dict(lang: str) -> Dict[str, str]:
    if lang in _DICT_CACHE:
        return _DICT_CACHE[lang]
    path = os.path.join(os.path.dirname(__file__), f"hud.{lang}.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"console.hud: missing dictionary file {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"console.hud: hud.{lang}.json must contain an object")
    _DICT_CACHE[lang] = data
    return data

def hud(status: str, key_or_text: str, **kwargs) -> None:
    """
    Пуш в HUD:
    - status: 'err'|'succ'|'ok' (для цвета в HUD)
    - key_or_text: ключ словаря ТЕКУЩЕГО языка ИЛИ прямой текст с {переменными}
    В HUD уходит ТОЛЬКО форматированный текст. В stdout не печатает.
    """
    if _HUD_PUSH is None:
        raise RuntimeError("console.hud: HUD push is not bound. Call console.bind(...) first.")
    if _LANG is None:
        raise RuntimeError("console.hud: language is not set. Call console.set_language(...).")
    if status not in _ALLOWED_STATUS:
        raise ValueError(f"console.hud: unsupported status '{status}', expected one of {sorted(_ALLOWED_STATUS)}")

    dct = _load_lang_dict(_LANG)
    template = dct.get(key_or_text)
    text = template if isinstance(template, str) else key_or_text

    # строгая подстановка — без молчаливых заглушек
    if "{" in text and "}" in text:
        text = text.format(**kwargs)

    # Пушим статус отдельно, но в HUD передаём только текст
    _HUD_PUSH(status, text)

def log(text: str) -> None:
    """Вывод только в stdout."""
    print(text)
