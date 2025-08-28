from __future__ import annotations
import re, sys, os, json, base64
from typing import Dict, List

AF_ROOT = os.path.dirname(__file__)  # .../core/engines/autofarm
# корень проекта: подняться на 4 уровня от zone_repo.py
PROJECT_ROOT = os.path.abspath(os.path.join(AF_ROOT, "..", "..", "..", ".."))
TEXTURES_MONSTERS = os.path.join(PROJECT_ROOT, "core", "textures", "lineage", "interlude", "monsters")

def _read_json_relaxed(path: str) -> dict:
    if not os.path.exists(path):
        sys.stderr.write(f"[autofarm] zones.json missing: {path}\n")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read()
        txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
        txt = re.sub(r"//.*?$", "", txt, flags=re.M)
        txt = re.sub(r",\s*([}\]])", r"\1", txt)
        return json.loads(txt)
    except Exception as e:
        sys.stderr.write(f"[autofarm] zones.json parse error: {path} :: {e}\n")
        return {}

def _read_json(path: str) -> Dict:
    if not os.path.exists(path): return {}
    with open(path, "r", encoding="utf-8") as f: return json.load(f)

def _zones_json(server: str) -> List[str]:
    # серверный, затем общий
    return [
        os.path.join(AF_ROOT, server, "zones.json"),
        os.path.join(AF_ROOT, "common", "zones.json"),
    ]

def _zones_root_galleries(server: str, zone_id: str) -> List[str]:
    return [
        os.path.join(AF_ROOT, server, "zones", zone_id, "gallery"),
        os.path.join(AF_ROOT, "common", "zones", zone_id, "gallery"),
    ]

def _zones_root(server: str, zone_id: str) -> List[str]:
    base = os.path.dirname(__file__)
    return [
        os.path.join(base, server, "zones", zone_id, "gallery"),
        os.path.join(base, "common", "zones", zone_id, "gallery"),
    ]
def _img_data_uri(abs_path: str) -> str | None:
    if not abs_path or not os.path.exists(abs_path):
        return None
    try:
        with open(abs_path, "rb") as f:
            b = f.read()
        return "data:image/png;base64," + base64.b64encode(b).decode("ascii")
    except Exception:
        return None

def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = s.replace("’", "'").replace("`", "'")
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", "'"):
            out.append("_")
    slug = "_".join(filter(None, "".join(out).split("_")))
    return slug or "unknown"

def _find_mon_icon(server: str, zone_id: str, slug: str) -> str | None:
    # 1) server-local
    cand = [
        os.path.join(AF_ROOT, server, "zones", zone_id, "monsters", f"{slug}.png"),
        os.path.join(AF_ROOT, "common", "monsters", f"{slug}.png"),
    ]
    for p in cand:
        if os.path.exists(p):
            return _img_data_uri(p)
    # 2) глобальные текстуры (рекурсивно по подпапкам локаций)
    root = TEXTURES_MONSTERS
    if os.path.isdir(root):
        target = f"{slug}.png"
        for dirpath, _dirs, files in os.walk(root):
            if target in files:
                return _img_data_uri(os.path.join(dirpath, target))
    return None

def _to_web_relative(abs_path: str) -> str:
    rel = os.path.relpath(abs_path, WEBUI)
    return rel.replace("\\", "/")

def _merge_dicts(a: Dict, b: Dict) -> Dict:
    d = dict(a); d.update(b); return d

def load_zones_merged(server: str) -> Dict:
    srv_path, com_path = _zones_json(server)[0], _zones_json(server)[1]
    # com_path укажет на common/zones.json
    common = _read_json_relaxed(com_path)
    srv    = _read_json_relaxed(srv_path)
    return _merge_dicts(common, srv)

def list_zones_declared(server: str, lang: str) -> List[Dict]:
    srv_path = _zones_json(server)[0]
    data = _read_json_relaxed(srv_path)
    out: List[Dict] = []
    for zid, meta in data.items():
        title = meta.get(f"title_{lang}") or meta.get("title") or zid
        out.append({"id": zid, "title": title})
    out.sort(key=lambda x: x["title"].lower())
    return out

def get_zone_info(server: str, zone_id: str, lang: str) -> Dict:
    data = load_zones_merged(server)
    meta = data.get(zone_id, {}) or {}
    title = meta.get(f"title_{lang}") or meta.get("title") or zone_id
    about = (meta.get("about") or {}).get(lang) or ""

    # галерея
    images: List[Dict] = []
    names = list(meta.get("gallery") or [])
    for root in _zones_root_galleries(server, zone_id):
        if not os.path.isdir(root):
            continue
        for name in names:
            p = os.path.join(root, name)
            if os.path.exists(p):
                src = _img_data_uri(p)
                if src:
                    images.append({"name": name, "src": src})
        if images:
            break

    # монстры
    mons_out: List[Dict] = []
    mons = (meta.get("monsters") or {})
    lst  = mons.get(lang) or mons.get("eng") or []
    for display in lst:
        mons_out.append({"slug": _slugify(display), "name": display})

    return {"id": zone_id, "title": title, "about": about, "images": images, "monsters": mons_out}
