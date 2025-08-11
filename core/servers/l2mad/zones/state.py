# core/servers/l2mad/zones/state.py
# Зоны и цвета для анализа состояния персонажа (HP/CP/MP)
from typing import Dict, Tuple, List

Zone = Tuple[int, int, int, int]
RGB = Tuple[int, int, int]

ZONES: Dict[str, Zone] = {
    "state": (160, 40, 440, 70),  # координаты области состояния
}

COLORS: Dict[str, List[Tuple[RGB, RGB]]] = {
    "hp": [
        ((180, 20, 20), (255, 60, 60)),
        ((140, 10, 10), (200, 40, 40)),
    ],
}
