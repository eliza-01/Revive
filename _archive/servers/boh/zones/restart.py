# _archive/servers/boh/zones/restart.py
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
    "yes_button": ["interface", "yes_button.png"],
    "pincode_init": ["interface", "pincode_init.png"],
    "disconnect_window": ["interface", "disconnect_window.png"],
    "settings_button": ["interface", "settings_button.png"],
    "restart_button": ["interface", "restart_button.png"],
    "apply_button": ["interface", "apply_button.png"],
    "account_characters_init": ["interface", "account_characters_init.png"],
    "relogin_button": ["interface", "relogin_button.png"],
    "enterGame_button": ["interface", "enterGame_button.png"],
    "login_accept_button": ["interface", "login_accept_button.png"],
    "enterServerOk_button": ["interface", "enterServerOk_button.png"],
    "start_button": ["interface", "start_button.png"],
    "closeCross_button": ["interface", "closeCross_button.png"],

    # pincode
    "num1": ["interface", "pincode", "num1.png"],
    "num2": ["interface", "pincode", "num2.png"],
    "num3": ["interface", "pincode", "num3.png"],
    "num4": ["interface", "pincode", "num4.png"],
    "num5": ["interface", "pincode", "num5.png"],
    "num6": ["interface", "pincode", "num6.png"],
    "num7": ["interface", "pincode", "num7.png"],
    "num8": ["interface", "pincode", "num8.png"],
    "num9": ["interface", "pincode", "num9.png"],
    "enter_pincode": ["interface", "pincode", "enter_pincode.png"],
}
