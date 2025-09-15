# core/engines/dashboard/server/boh/teleport/stabilize/stabilize_data.py
from typing import Dict, Tuple, List, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    "fullscreen": {"fullscreen": True},
    "state": {"left": 0, "top": 0, "width": 170, "height": 63},
    # верх-центр клиентской области: 500x120, отступ сверху = 1
    "target": {"centered_x": True, "width": 500, "height": 120, "top": 1},
}

TEMPLATES: Dict[str, List[str]] = {
    "target_init": ["common", "interface", "target_init.png"]
}
