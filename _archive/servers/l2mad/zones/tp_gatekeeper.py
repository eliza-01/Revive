# _archive/servers/l2mad/zones/tp_gatekeeper.py
from typing import Dict, Tuple
Zone = Tuple[int, int, int, int]

ZONES: Dict[str, Zone] = {
    "fullscreen": {"fullscreen": True},
    # добавите специальные зоны GK при нужде
}

TEMPLATES: Dict[str, list] = {
    "dashboard_init": ["dashboard", "dashboard_init.png"],
    "dashboard_is_locked": ["dashboard", "dashboard_is_locked.png"],
    "teleport_init": ["dashboard", "teleport", "dashboard_teleport_init.png"],
    "teleport_button": ["dashboard", "teleport", "dashboard_teleport_button.png"],
    # для GK позже добавите свои ключи
}
