# core/engines/autofarm/zone_repo.py
from __future__ import annotations
import re, sys, os, json, base64
from typing import Dict, List

AF_ROOT = os.path.dirname(__file__)  # .../core/engines/autofarm

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

def _zones_json(server: str) -> List[str]:
    # только новая структура + общий дефолт
    return [
        os.path.join(AF_ROOT, "server", server, "zones.json"),
        os.path.join(AF_ROOT, "server", "common", "zones.json"),
    ]

def _zones_root_galleries(server: str, zone_id: str) -> list[str]:
    base_srv = os.path.join(AF_ROOT, "server", server)
    base_com = os.path.join(AF_ROOT, "server", "common")
    return [
        os.path.join(base_srv, "zones", zone_id, "gallery"),
        os.path.join(base_srv, zone_id, "gallery"),
        os.path.join(base_com, "zones", zone_id, "gallery"),
        os.path.join(base_com, zone_id, "gallery"),
    ]

def _img_data_uri(p: str) -> str | None:
    if not p or not os.path.exists(p): return None
    with open(p, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")

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

def load_zones_merged(server: str) -> Dict:
    srv_path, com_path = _zones_json(server)
    common = _read_json_relaxed(com_path)
    srv    = _read_json_relaxed(srv_path)
    d = dict(common); d.update(srv)
    return d

def list_zones_declared(server: str, lang: str) -> list[dict]:
    srv_path, com_path = _zones_json(server)
    data = _read_json_relaxed(srv_path) or _read_json_relaxed(com_path)
    out = []
    for zid, meta in (data or {}).items():
        title = meta.get(f"title_{lang}") or meta.get("title") or zid
        out.append({"id": zid, "title": title})
    out.sort(key=lambda x: x["title"].lower())
    return out

def get_zone_info(server: str, zone_id: str, lang: str) -> Dict:
    data = load_zones_merged(server)
    meta  = data.get(zone_id, {}) or {}
    title = meta.get(f"title_{lang}") or meta.get("title") or zone_id
    about = (meta.get("about") or {}).get(lang) or ""

    images: List[Dict] = []
    names = list(meta.get("gallery") or [])
    exts  = (".png", ".jpg", ".jpeg")

    for root in _zones_root_galleries(server, zone_id):
        if not os.path.isdir(root):
            sys.stderr.write(f"[autofarm] gallery dir missing: {root}\n")
            continue
        for name in names:
            cands = [name] if name.lower().endswith(exts) else [name + e for e in exts]
            for fn in cands:
                p = os.path.join(root, fn)
                if os.path.exists(p):
                    src = _img_data_uri(p)
                    if src:
                        images.append({"name": os.path.basename(p), "src": src})
                        break
        if not images:
            try:
                for fn in sorted(os.listdir(root)):
                    if fn.lower().endswith(exts):
                        p = os.path.join(root, fn)
                        src = _img_data_uri(p)
                        if src:
                            images.append({"name": fn, "src": src})
            except Exception as e:
                sys.stderr.write(f"[autofarm] gallery scan error: {root} :: {e}\n")
        if images:
            break

    if not images:
        sys.stderr.write(f"[autofarm] gallery images not found for zone '{zone_id}' on server '{server}'\n")

    mons_out: List[Dict] = []
    mons = (meta.get("monsters") or {})
    lst  = mons.get(lang) or mons.get("eng") or []
    for display in lst:
        mons_out.append({"slug": _slugify(display), "name": display})

    return {"id": zone_id, "title": title, "about": about, "images": images, "monsters": mons_out}
