# core/logging/console.py
from __future__ import annotations
import json
import os
import threading
from typing import Optional, Callable

# === internal state ===
_HUD_PUSH: Optional[Callable[[str, str], None]] = None   # hud_push(status: str, text: str)
_HUD_CLEAR: Optional[Callable[[], None]] = None          # (опционально) явный очиститель HUD
_LANG = "eng"                 # язык подписи HUD (по умолчанию eng, переопределяется set_language)
_DICT_CACHE = {}              # кеш словарей по языку
_WARNED_LANGS = set()         # чтобы не спамить варнингами
_LOCK = threading.Lock()


def bind(*, hud_push=None, hud_clear=None):
    """
    Привязка функций вывода.
      hud_push(status: str, text: str)
      hud_clear()                      — (необязательно) явная очистка HUD

    Если hud_clear не передан — console.hud("clear") просто отправит
    в push статус "clear" с пустым текстом (fallback).
    """
    global _HUD_PUSH, _HUD_CLEAR
    _HUD_PUSH = hud_push
    _HUD_CLEAR = hud_clear


def set_language(lang: str):
    """Устанавливает язык для HUD-подписей. Без фаталов — если словаря нет, работаем без перевода."""
    global _LANG
    _LANG = str(lang or "").strip().lower() or "eng"


def _lang_dict_path(lang: str) -> str:
    base = os.path.dirname(__file__)
    return os.path.join(base, f"hud.{lang}.json")


def _load_lang_dict(lang: str) -> dict:
    """Безопасно грузит словарь HUD. Если файла нет — возвращает пустой словарь (fallback, без исключений)."""
    lang = (lang or "").strip().lower() or "eng"
    with _LOCK:
        if lang in _DICT_CACHE:
            return _DICT_CACHE[lang]

        path = _lang_dict_path(lang)
        try:
            with open(path, "r", encoding="utf-8") as f:
                dct = json.load(f) or {}
                _DICT_CACHE[lang] = dct
                return dct
        except FileNotFoundError:
            if lang not in _WARNED_LANGS:
                print(f"[console.hud] dictionary not found, fallback to raw text: {path}")
                _WARNED_LANGS.add(lang)
            _DICT_CACHE[lang] = {}
            return {}
        except Exception as e:
            if lang not in _WARNED_LANGS:
                print(f"[console.hud] dictionary load error ({path}): {e} — using raw text")
                _WARNED_LANGS.add(lang)
            _DICT_CACHE[lang] = {}
            return {}


def log(msg: str):
    """Простой лог в консоль (stdout)."""
    try:
        print(str(msg))
    except Exception:
        pass


def hud(status: str, text: str = ""):
    """
    Безопасный HUD-вызов.

    Варианты вызова:
      - console.hud("succ", "Готово")
      - console.hud("err", "Ошибка")
      - console.hud("clear")          ← очистить текущий HUD-баннер/внимание

    Поведение:
      - При обычном вызове: пытаемся перевести text через словарь текущего языка (если есть).
      - При status == "clear" и пустом text: если привязан явный _HUD_CLEAR, используем его;
        иначе шлём в _HUD_PUSH статус "clear" с пустым текстом (UI может трактовать это как очистку).
      - Если hud_push не привязан — дублируем в stdout, чтобы не терять события.
    """
    try:
        st = str(status or "")
    except Exception:
        st = ""

    # Быстрый путь очистки
    if st.lower() == "clear" and (text is None or text == ""):
        try:
            if callable(_HUD_CLEAR):
                _HUD_CLEAR()
            elif callable(_HUD_PUSH):
                _HUD_PUSH("clear", "")
            else:
                print("[HUD][clear]")
        except Exception as e:
            print(f"[console.hud] clear error: {e}")
        return

    raw_text = "" if text is None else str(text)

    # Перевод текста (если словарь доступен)
    try:
        dct = _load_lang_dict(_LANG)
        shown_text = dct.get(raw_text, raw_text)
    except Exception:
        shown_text = raw_text  # максимально безопасно

    try:
        if callable(_HUD_PUSH):
            _HUD_PUSH(st, shown_text)
        else:
            print(f"[HUD][{st}] {shown_text}")
    except Exception as e:
        print(f"[console.hud] push error: {e} | [{st}] {shown_text}")


def hud_clear():
    """Сокращение для очистки HUD: console.hud_clear()."""
    hud("clear")
