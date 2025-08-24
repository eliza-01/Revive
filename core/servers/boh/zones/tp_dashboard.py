# core/servers/l2mad/zones/tp_dashboard.py
from typing import Dict, Tuple

Zone = Tuple[int, int, int, int]

ZONES: Dict[str, Zone] = {
    # Общие зоны для поиска кнопок/списков
    "fullscreen":  {"fullscreen": True },
    # "confirm": (460, 500, 620, 560),

    # Gatekeeper диалог и область кликов
    # "gk_dialog": (220, 140, 900, 680),
}

# Ключи → части пути в resolver (конкретные локации выбираем динамически)
TEMPLATES: Dict[str, list] = {
    "dashboard_init": ["dashboard", "dashboard_init.png"],
    "dashboard_is_locked": ["dashboard", "dashboard_is_locked.png"],

    "teleport_init": ["dashboard", "teleport", "dashboard_teleport_init.png"],
    "teleport_button": ["dashboard", "teleport", "dashboard_teleport_button.png"],
}
