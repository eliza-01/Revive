# core/servers/l2mad/zones/restart.py
from typing import Dict, Tuple, Union, List

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    "fullscreen": {"fullscreen": True},
    "center_block": {"centered": True, "width": 600, "height": 400},
    "settings_block": {"right": 0, "bottom": 0, "width": 200, "height": 270},
}

TEMPLATES: Dict[str, List[str]] = {

    # клади реальные PNG в templates/ со своей структурой

    # Interface
    "settings_button": ["interface", "settings_button.png"],
    "restart_button": ["interface", "restart_button.png"],
    "apply_button": ["interface", "apply_button.png"],
    "relogin_button": ["interface", "relogin_button.png"],
    "enterGame_button": ["interface", "enterGame_button.png"],
    "login_accept_button": ["interface", "login_accept_button.png"],
    "enterServerOk_button": ["interface", "enterServerOk_button.png"],
    "start_button": ["interface", "start_button.png"],
    "closeCross_button": ["interface", "closeCross_button.png"],
}
