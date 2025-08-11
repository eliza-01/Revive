# core/servers/l2mad/zones/tp.py
from typing import Dict, Tuple, List

Zone = Tuple[int, int, int, int]
RGB = Tuple[int, int, int]

ZONES: Dict[str, Zone] = {
    # TODO: координаты кнопок/зон для ТП (dashboard или gatekeeper)
}

COLORS: Dict[str, List[Tuple[RGB, RGB]]] = {}
