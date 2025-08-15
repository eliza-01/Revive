from typing import Dict, Tuple, Union, List

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    "fullscreen": {"fullscreen": True},
    "center_block": {"centered": True, "width": 600, "height": 400},
    # добавляй зоны миникарты, компаса и т.п.
}

TEMPLATES: Dict[str, List[str]] = {
    # примеры; клади реальные PNG в templates/ со своей структурой
    "compass_n": ["world", "compass", "north.png"],
    "landmark_bridge": ["world", "landmarks", "bridge.png"],
    # ...

    #Varka_1
    "Varka_1_1": ["rows", "Goddard", "VarkaSilenosStronghold", "Varka_1", "1.png"],
    "Varka_1_2": ["rows", "Goddard", "VarkaSilenosStronghold", "Varka_1", "2.png"],
    "Varka_1_3": ["rows", "Goddard", "VarkaSilenosStronghold", "Varka_1", "3.png"],
}
