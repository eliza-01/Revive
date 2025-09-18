# core/engines/respawn/server/boh/respawn_data.py
# engines/respawn/server/<server>/respawn_data.py
# Зоны и шаблоны для подъёма после смерти (бывш. to_village).

from typing import Dict, Tuple, List, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    # Кнопка/баннер «встать/возродиться».
    # Центр окна 280x200 — поправишь при необходимости.
    "fullscreen": {"fullscreen": True},
    "death_banners": {"centered": True, "width": 520, "height": 320}, #   было 340x200
}

TEMPLATES: Dict[str, List[str]] = {
    "death_banner":  ["<lang>", "to_village_button.png"],
    "accept_button":  ["<lang>", "accept_button.png"],
    "reborn_banner": ["<lang>", "reborn_banner.png"],
}
