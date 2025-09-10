# core/engines/ui_guard/server/boh/ui_guard_data.py
from __future__ import annotations
from typing import Dict, Tuple

ZoneLTRB = Tuple[int, int, int, int]

# Где ищем. Для простоты — весь клиент (compute_zone_ltrb умеет "fullscreen": True)
ZONES: Dict[str, dict] = {
    "fullscreen": {"fullscreen": True},
}

# Карта "ключ страницы" -> имя файла в templates/<lang>/interface/pages/
PAGES: Dict[str, str] = {
    "dashboard_page": "dashboard_page.png",
    "inventory_page": "inventory_page.png",
    "skills_page": "skills_page.png",
    "map_page": "map_page.png",
    "map_page2": "map_page2.png",
    "quest_page": "quest_page.png",
    "status_page": "status_page.png",
    "clan_page": "clan_page.png",
    "menu_page": "menu_page.png",
    "actions_page": "actions_page.png",
    # добавляй по мере появления ассетов
}

# Какими кнопками закрываем.
# Файлы лежат в templates/<lang>/interface/buttons/
CLOSE_BUTTONS: Dict[str, str] = {
    "default": "default_cross_button.png",
    "dashboard": "close_dashboard_button.png",
}
