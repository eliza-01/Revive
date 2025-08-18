# core/servers/euro-pvp/zones/respawn.py
# Только "встать": дождаться баннера смерти, клик "В деревню", опционально подтверждение
from typing import Dict, Tuple, List

ZONES: Dict[str, Tuple[int, int, int, int]] = {
    "death_banner": (100, 80, 900, 260),
    "btn_to_village": (420, 420, 640, 480),
    "btn_confirm": (460, 500, 620, 560),
}

TEMPLATES = {
    "death_banner": "l2mad/death_banner",
    "to_village": "l2mad/btn_to_village",
    "confirm": "common/btn_confirm",
}

SEQUENCE: List[tuple] = [
    ("wait_template", "death_banner", "death_banner", 8000),
    ("click_template", "btn_to_village", "to_village", 3000),
    ("click_template", "btn_confirm", "confirm", 1500),  # может отсутствовать на сервере
]
