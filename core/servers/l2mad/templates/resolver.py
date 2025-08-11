# core/servers/l2mad/templates/resolver.py
"""
L2MAD template resolver.

Structure:
core/servers/l2mad/templates/<lang>/
  dashboard/
    dashboard_init.png
    dashboard_blocked.png
    teleport/
      dashboard_teleport_button.png
      villages/<Village>/<Location>.png
    buffer/
      dashboard_buffer_button.png
      dashboard_buffer_useProfile.png
      dashboard_buffer_useMage.png
      dashboard_buffer_useFighter.png
      dashboard_buffer_restoreHp.png
      dashboard_buffer_init.png
  death/
    to_village_button.png
"""
import os
from typing import List, Optional

_LANG_FALLBACK = "rus"

def _root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__)))

def _lang_root(lang: str) -> str:
    lang = (lang or _LANG_FALLBACK).lower()
    return os.path.join(_root(), lang)

def resolve(lang: str, *parts: str) -> Optional[str]:
    """
    Return absolute file path or None if not found.
    Example:
      resolve("rus", "dashboard", "teleport", "dashboard_teleport_button.png")
      resolve("rus", "death", "to_village_button.png")
      resolve("rus", "dashboard", "teleport", "villages", "Giran", "DragonValley.png")
    """
    path = os.path.join(_lang_root(lang), *parts)
    return path if os.path.isfile(path) else None

def exists(lang: str, *parts: str) -> bool:
    return resolve(lang, *parts) is not None

def listdir(lang: str, *parts: str) -> List[str]:
    path = os.path.join(_lang_root(lang), *parts)
    try:
        return sorted(os.listdir(path))
    except Exception:
        return []

# ---------- Convenience shortcuts ----------

def death_to_village_button(lang: str) -> Optional[str]:
    return resolve(lang, "death", "to_village_button.png")

def dashboard_init(lang: str) -> Optional[str]:
    return resolve(lang, "dashboard", "dashboard_init.png")

def dashboard_blocked(lang: str) -> Optional[str]:
    return resolve(lang, "dashboard", "dashboard_blocked.png")

def dashboard_teleport_button(lang: str) -> Optional[str]:
    return resolve(lang, "dashboard", "teleport", "dashboard_teleport_button.png")

def dashboard_buffer_button(lang: str) -> Optional[str]:
    return resolve(lang, "dashboard", "buffer", "dashboard_buffer_button.png")

def dashboard_buffer_mode(lang: str, mode: str) -> Optional[str]:
    mode = (mode or "profile").lower()
    file = {
        "profile": "dashboard_buffer_useProfile.png",
        "mage": "dashboard_buffer_useMage.png",
        "fighter": "dashboard_buffer_useFighter.png",
    }.get(mode)
    return resolve(lang, "dashboard", "buffer", file) if file else None

def dashboard_buffer_restore_hp(lang: str) -> Optional[str]:
    return resolve(lang, "dashboard", "buffer", "dashboard_buffer_restoreHp.png")

def dashboard_buffer_init(lang: str) -> Optional[str]:
    return resolve(lang, "dashboard", "buffer", "dashboard_buffer_init.png")

def teleport_villages(lang: str) -> List[str]:
    return listdir(lang, "dashboard", "teleport", "villages")

def teleport_locations(lang: str, village: str) -> List[str]:
    return listdir(lang, "dashboard", "teleport", "villages", village)

def teleport_location(lang: str, village: str, location_png_name: str) -> Optional[str]:
    return resolve(lang, "dashboard", "teleport", "villages", village, location_png_name)
