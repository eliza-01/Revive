# _archive/servers/l2mad/zones/state.py
from typing import Dict, Tuple, List

Zone = Tuple[int, int, int, int]
RGB = Tuple[int, int, int]

# Одна зона STATE (в ней лежат HP/CP/MP). Координаты в client-координатах окна.
ZONES: Dict[str, Zone] = {
    "state": (0, 0, 175, 85),
}

# Цвета для HP: «живые» и «мёртвые» сегменты полосы. Списки RGB-точек.
COLORS: Dict[str, List[RGB]] = {
    "hp_alive_rgb": [
        (154, 41, 30), (132, 28, 16), (165, 48, 33), (148, 36, 24),
        (159, 44, 30), (126, 50, 38), (134, 88, 79), (140, 97, 90),
        (123, 69, 57), (123, 60, 49),
    ],
    "hp_dead_rgb": [
        (41, 28, 8), (49, 24, 16), (66, 40, 33), (49, 32, 24),
        (55, 40, 35), (57, 44, 41), (63, 47, 41), (74, 56, 57),
    ],
}

# Допуск в цвете для маскирования (в единицах 0..255).
HP_COLOR_TOLERANCE: int = 1
