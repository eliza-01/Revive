# core/engines/autofarm/skill_repo.py
from __future__ import annotations
import os, json, sys, base64
from typing import Dict, List

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))  # -> core/
AF_ROOT = os.path.dirname(__file__)  # core/engines/autofarm
WEBUI = os.path.abspath(os.path.join(AF_ROOT, "..", "..", "..", "app", "webui"))

def _read_json(path: str) -> Dict:
    if not os.path.exists(path):
        sys.stderr.write(f"[autofarm] professions.json missing: {path}\n")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        sys.stderr.write(f"[autofarm] professions.json bad JSON: {path} :: {e}\n")
        return {}

def _prof_path() -> str:
    return os.path.join(AF_ROOT, "common", "professions.json")

def professions_json_path() -> str:
    return os.path.join(AF_ROOT, "common", "professions.json")

def list_professions(lang: str) -> list[dict]:
    path = os.path.join(AF_ROOT, "common", "professions.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f) or {}
    out = []
    for slug, meta in data.items():
        t = (meta.get(f"title_{lang}") or meta.get("title")
             or " ".join(w.capitalize() for w in slug.split("_")))
        out.append({"slug": slug, "title": t})
    out.sort(key=lambda x: x["title"].lower())
    return out

def debug_professions():
    path = professions_json_path()
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    keys = []
    err = None
    if exists:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            keys = sorted(data.keys())
        except Exception as e:
            err = str(e)
    return {"path": path, "exists": exists, "size": size, "keys": keys, "error": err}

def _catalog_path() -> str:
    return os.path.join(AF_ROOT, "common", "skills_catalog.json")

def _icon_path(server: str, slug: str) -> str | None:
    candidates = [
        os.path.join(AF_ROOT, server, "skills", f"{slug}.png"),
        os.path.join(AF_ROOT, "common", "skills", f"{slug}.png"),
    ]
    for p in candidates:
        if os.path.exists(p): return p
    return None

def _icon_data_uri(server: str, slug: str) -> str | None:
    candidates = [
        os.path.join(AF_ROOT, server, "skills", f"{slug}.png"),
        os.path.join(AF_ROOT, "common", "skills", f"{slug}.png"),
    ]
    for p in candidates:
        if os.path.exists(p):
            with open(p, "rb") as f:
                b = f.read()
            return "data:image/png;base64," + base64.b64encode(b).decode("ascii")
    return None

def _to_web_relative(abs_path: str) -> str:
    rel = os.path.relpath(abs_path, WEBUI)
    return rel.replace("\\", "/")

def list_skills(profession: str, types: List[str], lang: str, server: str) -> List[Dict]:
    """
    Возвращает [{slug, name, icon}] для выбранной профессии.
    types: ["attack"] или ["attack","debuff",...]
    """
    profs = _read_json(_prof_path())
    cat = _read_json(_catalog_path())
    meta = profs.get(profession, {}).get("skills", {})
    slugs: List[str] = []
    for t in types:
        arr = (meta.get(t, {}) or {}).get(lang, []) or []
        slugs.extend(arr)
    out: List[Dict] = []
    for slug in slugs:
        name = (cat.get(slug, {}) or {}).get(lang) or slug
        icon_src = _icon_data_uri(server, slug)   # ← было через _to_web_relative(...)
        out.append({"slug": slug, "name": name, "icon": icon_src})
    return out
