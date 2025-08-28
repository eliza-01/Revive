from __future__ import annotations
import re, sys, os, json
from typing import Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))  # -> core/
WEBUI = os.path.join(ROOT, "app", "webui")

def _read_json_relaxed(path: str) -> dict:
    if not os.path.exists(path):
        sys.stderr.write(f"[autofarm] zones.json missing: {path}\n")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        # убрать // и /* */ комментарии
        txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
        txt = re.sub(r"//.*?$", "", txt, flags=re.M)
        # убрать хвостовые запятые перед } или ]
        txt = re.sub(r",\s*([}\]])", r"\1", txt)
        return json.loads(txt)
    except Exception as e:
        sys.stderr.write(f"[autofarm] zones.json parse error: {path} :: {e}\n")
        return {}

def _read_json(path: str) -> Dict:
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f: return json.load(f)

def _zones_json(server: str) -> List[str]:
    base = os.path.dirname(__file__)  # .../core/engines/autofarm
    return [
        os.path.join(base, server, "zones.json"),
        os.path.join(base, "common", "zones.json"),
    ]

def _zones_root(server: str, zone_id: str) -> List[str]:
    base = os.path.dirname(__file__)
    return [
        os.path.join(base, server, "zones", zone_id, "gallery"),
        os.path.join(base, "common", "zones", zone_id, "gallery"),
    ]

def _to_web_relative(abs_path: str) -> str:
    rel = os.path.relpath(abs_path, WEBUI)
    return rel.replace("\\", "/")

def _merge_dicts(a: Dict, b: Dict) -> Dict:
    d = dict(a); d.update(b); return d

def load_zones_merged(server: str) -> Dict:
    # серверный поверх общего
    common = _read_json(_zones_json("common")[1])
    srv = _read_json(_zones_json(server)[0])
    return _merge_dicts(common, srv)

def get_zone_info(server: str, zone_id: str, lang: str) -> Dict:
    data = load_zones_merged(server)
    meta = data.get(zone_id, {}) or {}
    title = meta.get(f"title_{lang}") or meta.get("title") or zone_id
    about = (meta.get("about") or {}).get(lang) or ""
    imgs: List[Dict] = []
    # собрать галерею
    names = list(meta.get("gallery") or [])
    for root in _zones_root(server, zone_id):
        if not os.path.isdir(root): continue
        for name in names:
            p = os.path.join(root, name)
            if os.path.exists(p):
                imgs.append({"abs": p, "src": _to_web_relative(p), "name": name})
        if imgs: break
    return {"id": zone_id, "title": title, "about": about, "images": imgs}

def list_zones_declared(server: str, lang: str) -> list[dict]:
    base = os.path.dirname(__file__)
    path = os.path.join(base, server, "zones.json")
    data = _read_json_relaxed(path)
    out = []
    for zid, meta in data.items():
        title = meta.get(f"title_{lang}") or meta.get("title") or zid
        out.append({"id": zid, "title": title})
    out.sort(key=lambda x: x["title"].lower())
    return out