# core/engines/ui_guard/server/boh/ui_guard_data.py
from __future__ import annotations
from typing import Dict, Tuple

ZoneLTRB = Tuple[int, int, int, int]

# Где ищем. Для простоты — весь клиент (compute_zone_ltrb умеет "fullscreen": True)
ZONES: Dict[str, dict] = {
    "fullscreen": {"fullscreen": True},
}

# Карта "ключ страницы" -> имя файла в templates/<lang>/interface/pages/
PAGES_BLOCKER: Dict[str, str] = {
    "inventory_page": "inventory_page.png",
    "skills_page": "skills_page.png",
    "map_page": "map_page.png",
    "map_page2": "map_page2.png",
    "quest_page": "quest_page.png",
    "status_page": "status_page.png",
    "clan_page": "clan_page.png",
    "menu_page": "menu_page.png",
    "actions_page": "actions_page.png",
    "macros_page": "macros_page.png",
    # добавляй по мере появления ассетов
}

# Какими кнопками закрываем.
# Файлы лежат в templates/<lang>/interface/buttons/
PAGES_CLOSE_BUTTONS: Dict[str, str] = {
    "pages_close_button": "default_close_button.png",
}

DASHBOARD_BLOCKER: Dict[str, str] = {
    "dashboard_blocker": "dashboard_page.png",
    "dashboard_blocker_close_button": "dashboard_close_button.png",
}

LANGUAGE_BLOCKER: Dict[str, str] = {
    "language_blocker": "wrong_word_popup.png",
    "language_blocker_close_button": "wrong_word_accept_button.png",
}

DISCONNECT_BLOCKER: Dict[str, str] = {
    "disconnect_blocker": "disconnect_popup.png",
    "disconnect_blocker_close_button": "disconnect_accept_button.png",
}

DEATH: Dict[str, str] = {
    "-": "-.png",
    "--": "--.png",
}
