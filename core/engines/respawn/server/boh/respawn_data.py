# core/engines/respawn/server/boh/respawn_data.py
# engines/respawn/server/<server>/respawn_data.py
# Зоны и шаблоны для подъёма после смерти (бывш. to_village).

from typing import Dict, Tuple, List, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    # Кнопка/баннер «встать/возродиться».
    # Центр окна 280x200 — поправишь при необходимости.
    "death_banners": {"fullscreen": True, "width": 280, "height": 200},
}

# Пути до шаблонов через серверный resolver
# (см. core/servers/<server>/templates/resolver.py)
# Используем маркер "<lang>", который движок заменит на фактический язык.
TEMPLATES: Dict[str, List[str]] = {
    # приоритет: сначала то, чем реально пользуетесь
    "reborn_banner": ["<lang>", "reborn_window.png"],
    "death_banner":  ["<lang>", "to_village_button.png"],
    "accept_button":  ["<lang>", "accept_button.png"],
    "decline_button":  ["<lang>", "decline_button.png"],
    # при необходимости добавь ещё варианты:
    # "confirm": ["<lang>", "confirm.png"],
}
