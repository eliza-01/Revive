from __future__ import annotations
import json
import os
import threading

# === internal state ===
_HUD_PUSH = None              # функция-пушер HUD: hud_push(status: str, text: str)
_LANG = "eng"                 # язык подписи HUD (по умолчанию eng, переопределяется set_language)
_DICT_CACHE = {}              # кеш словарей по языку
_WARNED_LANGS = set()         # чтобы не спамить варнингами
_LOCK = threading.Lock()


def bind(*, hud_push=None):
    """Привязка функций вывода (сейчас только HUD)."""
    global _HUD_PUSH
    _HUD_PUSH = hud_push


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
            # Однократно предупредим в stdout и продолжим без перевода
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


def hud(status: str, text: str):
    """
    Безопасный HUD-вызов.
    - Пытаемся перевести текст через словарь текущего языка (если есть).
    - Если hud_push не привязан — дублируем в stdout, чтобы не терять события.
    """
    status = str(status or "")
    raw_text = str(text or "")

    try:
        dct = _load_lang_dict(_LANG)
        # Если ключ есть — переводим, если нет — показываем как есть
        shown_text = dct.get(raw_text, raw_text)
    except Exception:
        shown_text = raw_text  # абсолютно безопасный фолбэк

    try:
        if callable(_HUD_PUSH):
            _HUD_PUSH(status, shown_text)
        else:
            print(f"[HUD][{status}] {shown_text}")
    except Exception as e:
        # Последний рубеж — не уронить поток из-за HUD
        print(f"[console.hud] push error: {e} | [{status}] {shown_text}")
