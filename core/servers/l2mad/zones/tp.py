# core/servers/l2mad/zones/tp.py
from typing import Dict, Tuple

Zone = Tuple[int, int, int, int]

ZONES: Dict[str, Zone] = {
    # Общие зоны для поиска кнопок/списков
    "dashboard_tab": (10, 10, 240, 120),
    "dashboard_body": (250, 120, 950, 720),
    "confirm": (460, 500, 620, 560),

    # Gatekeeper диалог и область кликов
    "gk_dialog": (220, 140, 900, 680),
}

# Ключи → части пути в resolver (конкретные локации выбираем динамически)
TEMPLATES: Dict[str, list] = {
    "tab_tp": ["dashboard", "teleport", "dashboard_teleport_button.png"],
    "confirm": ["dashboard", "buffer", "dashboard_buffer_init.png"],  # заменишь на реальный confirm, если есть
}
