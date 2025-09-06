# core/engines/player_state/server/boh/state_data.py
from typing import Dict, Tuple, List

Zone = Tuple[int, int, int, int]
RGB = Tuple[int, int, int]

# Координаты зоны STATE (HP/CP/MP) в client-координатах окна.
ZONES: Dict[str, Zone] = {
    "state": (0, 0, 170, 63),
}

# Цвета для HP: «живые» и «мёртвые» сегменты полосы. Списки RGB-точек.
COLORS: Dict[str, List[RGB]] = {
    "hp_alive_rgb": [
        (130, 87, 80), (142, 96, 92), (130, 77, 70), (127, 62, 56),
        (125, 53, 44), (121, 28, 17), (137, 32, 21), (148, 37, 24),
        (162, 44, 31), (162, 52, 40),
    ],
    "hp_dead_rgb": [
        (64, 52, 48), (69, 60, 57), (59, 45, 45), (52, 36, 34),
        (56, 32, 28), (61, 37, 32), (67, 41, 36), (71, 42, 37),
    ],
}

# Отдельные допуски по цвету (0..255)
HP_TOLERANCE_ALIVE: int = 1
HP_TOLERANCE_DEAD: int = 1

# Период опроса по умолчанию (сек.)
DEFAULT_POLL_INTERVAL: float = 1.0
