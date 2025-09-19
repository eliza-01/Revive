# core/engines/dashboard/server/boh/dashboard_data.py
from typing import Dict, Tuple, List, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    # common
    "fullscreen": {"fullscreen": True, "width": 280, "height": 200},
    # buffer
    "current_buffs": {"left": 160, "top": 0, "width": 360, "height": 130},
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
    "dashboard_buffer_archer": ["<lang>", "buffer", "dashboard_buffer_archer.png"],
    "dashboard_buffer_restoreHp": ["<lang>", "buffer", "dashboard_buffer_restoreHp.png"],
    "target_player_init": ["<lang>", "buffer", "target_player_init.png"],
    # dashboard_teleport
    "dashboard_teleport_init": ["<lang>", "teleport", "dashboard_teleport_init.png"],
    # interface
    "target_init": ["common", "interface", "target_init.png"]
}
TELEPORT_CATEGORIES: Dict[str, List[str]] = {
    # кнопки перехода в раздел с городами/деревнями
    "towns": ["<lang>", "teleport", "towns.png"],
    "villages": ["<lang>", "teleport", "villages.png"],
}
TELEPORT_TOWNS: Dict[str, List[str]] = {
    "towns_init": ["<lang>", "teleport", "towns", "towns_init.png"],
    # кнопки перехода в раздел конкретного города
    "Goddard": ["<lang>", "teleport", "towns", "Goddard.png"],
    "Goddard_init": ["<lang>", "teleport", "towns", "Goddard", "Goddard_init.png"],
    "Rune": ["<lang>", "teleport", "towns", "Rune.png"],
    "Rune_init": ["<lang>", "teleport", "towns", "Rune", "Rune_init.png"],
    "Giran": ["<lang>", "teleport", "towns", "Giran.png"],
    "Giran_init": ["<lang>", "teleport", "towns", "Giran", "Giran_init.png"],
    "Aden": ["<lang>", "teleport", "towns", "Aden.png"],
    "Aden_init": ["<lang>", "teleport", "towns", "Aden", "Aden_init.png"],
}
TELEPORT_VILLAGES: Dict[str, List[str]] = {
    "villages_init": ["<lang>", "teleport", "villages", "villages_init.png"],
    # кнопки перехода в раздел конкретной деревни
    "TalkingIsland": ["<lang>", "teleport", "villages", "TalkingIsland.png"],
    "TalkingIsland_init": ["<lang>", "teleport", "villages", "TalkingIsland", "TalkingIsland.png"],
}
TELEPORT_LOCATIONS: Dict[str, List[str]] = {
    # кнопки перемещения в город, как локацию
    "Goddard": ["<lang>", "teleport", "towns", "Goddard", "Goddard.png"],
    "Rune": ["<lang>", "teleport", "towns", "Rune", "Rune.png"],
    "Giran": ["<lang>", "teleport", "towns", "Giran", "Giran.png"],
    # dashboard_teleport_towns_Goddard
    "VarkaSilenosStronghold": ["<lang>", "teleport", "towns", "Goddard", "VarkaSilenosStronghold.png"],
    "PrimevalIsle": ["<lang>", "teleport", "towns", "Rune", "PrimevalIsle.png"],
    "DragonValley": ["<lang>", "teleport", "towns", "Giran", "DragonValley.png"],
    # dashboard_teleport_towns_Aden
    "SilentValley": ["<lang>", "teleport", "towns", "Aden", "SilentValley.png"],
}
# Разделы бафов
BUFFS: Dict[str, List[str]] = {
    "mental_shield": ["common", "buffer", "icons", "buffs", "mental_shield.png"],
}
DANCES: Dict[str, List[str]] = {
    "dance_of_concentration": ["common", "buffer", "icons", "dances", "dance_of_concentration.png"],
    "dance_of_siren": ["common", "buffer", "icons", "dances", "dance_of_siren.png"]
}
SONGS: Dict[str, List[str]] = {
    "song_of_earth": ["common", "buffer", "icons", "songs", "song_of_earth.png"],
    "song_of_vitality": ["common", "buffer", "icons", "songs", "song_of_vitality.png"]
}
