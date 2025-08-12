# core/servers/l2mad/zones/buff.py
from typing import Dict, Tuple, List, Union

# Зоны могут быть кортежом (l,t,r,b) в client-координатах
# или словарём {"fullscreen":True} | {"centered":True,"width":W,"height":H} | {"left","top","width","height"}
ZoneLTRB = Tupble[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    # Зона, где ищем иконки/кнопки в дашборде
    "dashboard_body": {"fullscreen": True },
    # "confirm": {"fullscreen": True },
    # иногда удобно искать по центру
    # "center_block": {"centered": True, "width": 500, "height": 400},
}

# Ключ → список частей пути для серверного resolver'а
TEMPLATES: Dict[str, List[str]] = {
    "dashboard_init": ["dashboard", "dashboard_init.png"],
    "dashboard_blocked": ["dashboard", "dashboard_blocked.png"],

    "buffer_button": ["dashboard", "buffer", "dashboard_buffer_button.png"],
    "buffer_init":   ["dashboard", "buffer", "dashboard_buffer_init.png"],
    "buffer_mode_profile": ["dashboard", "buffer", "dashboard_buffer_useProfile.png"],
    "buffer_mode_mage":    ["dashboard", "buffer", "dashboard_buffer_useMage.png"],
    "buffer_mode_fighter": ["dashboard", "buffer", "dashboard_buffer_useFighter.png"],
    "buffer_restore_hp":   ["dashboard", "buffer", "dashboard_buffer_restoreHp.png"],
}
