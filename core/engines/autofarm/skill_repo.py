# core/engines/autofarm/skill_repo.py
from __future__ import annotations
import os, json, sys, base64  # noqa: F401 (sys оставлен, если где-то импортируется модуль и ожидает его)
from typing import Dict, List

from core.logging import console  # ← новый логгер

AF_ROOT = os.path.dirname(__file__)  # core/engines/autofarm
WEBUI = os.path.abspath(os.path.join(AF_ROOT, "..", "..", "..", "app", "webui"))

def _read_json(path: str) -> Dict:
    if not os.path.exists(path):
        console.log(f"[autofarm] JSON missing: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        console.log(f"[autofarm] bad JSON: {path} :: {e}")
        return {}

def _prof_path() -> str:
    return os.path.join(AF_ROOT, "server", "common", "professions.json")

def debug_professions():
    """
    Диагностика наличия/целостности файла с профессиями.
    Возвращает словарь: {path, exists, size, keys, error}
    """
    path = professions_json_path()  # указывает на AF_ROOT/common/professions.json
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    keys = []
    err = None
    if exists:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if isinstance(data, dict):
                keys = sorted(data.keys())
            else:
                err = "professions.json is not a dict"
        except Exception as e:
            err = str(e)
    return {"path": path, "exists": exists, "size": size, "keys": keys, "error": err}

def professions_json_path() -> str:
    return _prof_path()

def list_professions(lang: str) -> list[dict]:
    data = _read_json(_prof_path())
    out = []
    for slug, meta in data.items():
        t = (meta.get(f"title_{lang}") or meta.get("title")
             or " ".join(w.capitalize() for w in slug.split("_")))
        out.append({"slug": slug, "title": t})
    out.sort(key=lambda x: x["title"].lower())
    return out

def _catalog_path() -> str:
    return os.path.join(AF_ROOT, "server", "common", "skills_catalog.json")

def _icon_data_uri(server: str, slug: str) -> str | None:
    candidates = [
        os.path.join(AF_ROOT, "server", server, "skills", f"{slug}.png"),
        os.path.join(AF_ROOT, "server", "common", "skills", f"{slug}.png"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "rb") as f:
                b = f.read()
            return "data:image/png;base64," + base64.b64encode(b).decode("ascii")
    # отсутствие иконки — норм, без спама в лог
    return None

def list_skills(profession: str, types: List[str], lang: str, server: str) -> List[Dict]:
    """
    Возвращает [{slug, name, icon}] для выбранной профессии.
    types: ["attack"] или ["attack","debuff",...]
    """
    profs = _read_json(_prof_path())
    cat = _read_json(_catalog_path())
    meta = (profs.get(profession, {}) or {}).get("skills", {}) or {}
    slugs: List[str] = []
    for t in types:
        arr = (meta.get(t, {}) or {}).get(lang, []) or []
        slugs.extend(arr)
    out: List[Dict] = []
    for slug in slugs:
        name = (cat.get(slug, {}) or {}).get(lang) or slug
        icon_src = _icon_data_uri(server, slug)
        out.append({"slug": slug, "name": name, "icon": icon_src})
    return out
