# core/engines/ui_guard/server/boh/ui_guard_data.py
from typing import Dict, List, Tuple, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {
    "fullscreen": {"fullscreen": True},
}

# ключи страниц и имена файлов в templates/<lang>/interface/pages/
PAGES: Dict[str, str] = {
    "dashboard_page": "dashboard_page.png",
    "inventory_page": "inventory_page.png",
    "map_page":       "map_page.png",
    "map_page2":      "map_page2.png",
    "skills_page":    "skills_page.png",
    "status_page":    "status_page.png",
    "clan_page":      "clan_page.png",
    "actions_page":   "actions_page.png",
    "menu_page":      "menu_page.png",
    "quest_page":     "quest_page.png",
}

# кнопки закрытия (templates/<lang>/interface/buttons/)
CLOSE_BUTTONS: Dict[str, str] = {
    "default":   "default_cross_button.png",
    "dashboard": "close_dashboard_button.png",
}
