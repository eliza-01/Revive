# core/engines/autofarm/zone_repo.py
from __future__ import annotations
import os, json
from typing import Dict, Any, List
from pathlib import Path

AF_ROOT = os.path.join("core", "engines", "autofarm")

def _zones_json_candidates(server: str) -> List[str]:
    # серверный приоритет + общий fallback (ИМЕННО так)
    return [
        os.path.join(AF_ROOT, "server", server, "zones.json"),
        os.path.join(AF_ROOT, "server", "common", "zones.json"),
    ]

def _read_zones_map(server: str) -> Dict[str, Any]:
    for p in _zones_json_candidates(server):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def _pick_title(z: dict, lang: str) -> str:
    lang = (lang or "eng").lower()
    return z.get(f"title_{lang}") or z.get("title_eng") or z.get("title_rus") or z.get("title") or ""

def _pick_about(z: dict, lang: str) -> str:
    lang = (lang or "eng").lower()
    about = z.get("about")
    if isinstance(about, dict):
        return about.get(lang) or about.get("eng") or about.get("rus") or ""
    if isinstance(about, str):
        return about
    return ""

def _pick_full_names(z: dict, lang: str) -> List[str]:
    """
    РОВНО как было: UI показывает *полные* имена.
    Приоритет ключей: <lang>_full → eng_full → rus_full → <lang> → eng → rus.
    """
    lang = (lang or "eng").lower()
    mons = z.get("monsters") or {}
    for key in (f"{lang}_full", "eng_full", "rus_full", lang, "eng", "rus"):
        arr = mons.get(key)
        if isinstance(arr, list) and arr:
            return [str(x) for x in arr if x]
    return []

def _zone_gallery(server: str, zone_id: str, z: dict) -> List[Dict[str, str]]:
    """
    Картинки (если объявлены) ищем в:
      core/engines/autofarm/server/<server>/zones/<zone_id>/<name>
    Отдаём file:// URI, как раньше.
    """
    base = Path("core") / "engines" / "autofarm" / "server" / server / "zones" / zone_id
    out: List[Dict[str, str]] = []
    gallery = z.get("gallery") or []
    if not isinstance(gallery, list):
        return out
    for name in gallery:
        p = base / str(name)
        try:
            if p.exists():
                out.append({"name": str(name), "src": p.resolve().as_uri()})
        except Exception:
            pass
    return out

def list_zones_declared(server: str, lang: str = "eng") -> List[Dict[str, Any]]:
    """
    Список объявленных зон (для дропа в селект).
    Тайтл берём из title_eng/title_rus — это НАЗВАНИЕ ЗОНЫ, не список мобов.
    """
    data = _read_zones_map(server)
    out: List[Dict[str, Any]] = []
    for zid, z in (data or {}).items():
        if not isinstance(z, dict):
            continue
        title = _pick_title(z, lang) or zid
        out.append({"id": zid, "title": title})
    return out

def get_zone_info(server: str, zone_id: str, lang: str = "eng") -> Dict[str, Any]:
    """
    Полная инфа для UI:
      - title/about/images
      - monsters → ИМЕННО *full*-имена (как раньше использовал UI)
    """
    data = _read_zones_map(server)
    z = (data or {}).get(zone_id) or {}
    return {
        "id": zone_id,
        "title": _pick_title(z, lang) or zone_id,
        "about": _pick_about(z, lang),
        "images": _zone_gallery(server, zone_id, z),
        "monsters": _pick_full_names(z, lang),   # ВАЖНО: сюда кладём FULL
    }
