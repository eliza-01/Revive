# core/servers/boh/zones/buffs_state.py
from typing import Dict, Tuple, List, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    "buff_bar": {"left": 180, "top": 0, "width": 400, "height": 80},
    # "buff_bar": {"fullscreen": True},  # для теста
}

TEMPLATES: Dict[str, List[str]] = {
    # примеры. положи реальные png и поправь имена
    "buff_icon_shield": ["buffs", "icons", "shield.png"],
    "buff_icon_blessedBody":     ["buffs", "icons", "blessedBody.png"],
    # добавляй свои…
}
