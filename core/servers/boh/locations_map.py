# core/servers/boh/locations_map.py
# Категории/локации для ТП читаем из структуры templates.
from typing import List, Dict
from .templates import resolver as tpl  # ← относительный импорт

def get_categories(lang: str = "rus") -> List[Dict]:
    out: List[Dict] = []
    villages = tpl.listdir(lang, "dashboard", "teleport", "villages")
    for v in villages:
        if v.startswith("."):
            continue
        out.append({
            "id": v,
            "display_rus": v,
            "display_eng": v,
        })
    return out

def get_locations(category_id: str, lang: str = "rus") -> List[Dict]:
    out: List[Dict] = []
    locs = tpl.listdir(lang, "dashboard", "teleport", "villages", category_id)
    for f in locs:
        if not f.lower().endswith(".png"):
            continue
        name = f.rsplit(".", 1)[0]
        out.append({
            "id": name,
            "display_rus": name,
            "display_eng": name,
            "filename": f,
        })
    return out
