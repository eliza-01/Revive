from typing import Dict, Tuple, List, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    # common
    "fullscreen": {"fullscreen": True, "width": 280, "height": 200},
    # buffer
    "current_buffs": (160, 0, 350, 130),
    # "centered_zone": {"centered": True, "width": 200, "height": 200},
}

# Пути до шаблонов через серверный resolver
TEMPLATES: Dict[str, List[str]] = {
    # dashboard_main
    "dashboard_init": ["<lang>", "main", "dashboard_init.png"],
    "dashboard_is_locked_1": ["<lang>", "main", "dashboard_is_locked_1.png"],
    "dashboard_is_locked_2": ["<lang>", "main", "dashboard_is_locked_2.png"],
    "dashboard_buffer_button": ["<lang>", "main", "dashboard_buffer_button.png"],
    "dashboard_teleport_button": ["<lang>", "main", "dashboard_teleport_button.png"],
    # dashboard_buffer
    "dashboard_buffer_init": ["<lang>", "buffer", "dashboard_buffer_init.png"],
    "dashboard_buffer_profile": ["<lang>", "buffer", "dashboard_buffer_profile.png"],
    "dashboard_buffer_fighter": ["<lang>", "buffer", "dashboard_buffer_fighter.png"],
    "dashboard_buffer_mage": ["<lang>", "buffer", "dashboard_buffer_mage.png"],
    "dashboard_buffer_restoreHp": ["<lang>", "buffer", "dashboard_buffer_restoreHp.png"],
    "target_player_init": ["<lang>", "buffer", "target_player_init.png"],
    # dashboard_teleport
    "dashboard_teleport": ["<lang>", "teleport", "dashboard_teleport_init.png"],
    # dashboard_teleport_towns
    "dashboard_teleport_towns": ["<lang>", "teleport", "towns", "towns.png"],
    # dashboard_teleport_towns_Goddard
    "dashboard_teleport_Goddard": ["<lang>", "teleport", "towns", "Goddard", "Goddard.png"],
    "dashboard_teleport_VarkaSilenosStronghold": ["<lang>", "teleport", "towns", "Goddard", "VarkaSilenosStronghold.png"],
    # dashboard_teleport_towns_Rune
    "dashboard_teleport_Rune": ["<lang>", "teleport", "towns", "Rune", "Rune.png"],
    "dashboard_teleport_PrimevalIsle": ["<lang>", "teleport", "towns", "Rune", "PrimevalIsle.png"],
    # dashboard_teleport_towns_Giran
    "dashboard_teleport_Giran": ["<lang>", "teleport", "towns", "Giran", "Giran.png"],
    "dashboard_teleport_DragonValley": ["<lang>", "teleport", "towns", "Giran", "DragonValley.png"],
}
