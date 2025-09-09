# core/servers/boh/zones/respawn.py
# Зоны и шаблоны для подъёма после смерти.
from typing import Dict, Tuple, List, Union

ZoneLTRB = Tuple[int, int, int, int]
ZoneDecl = Union[ZoneLTRB, dict]

ZONES: Dict[str, ZoneDecl] = {

    # Кнопка «В деревню». Поддерживаем центрирование через dict.
    "to_village": {"centered": True, "width": 200, "height": 200},

    # Баннер/область смерти, если нужно ждать появления (опционально)
    # "death_banner": (100, 80, 900, 260),
    # Подтверждение (если есть). Можно указать фикс/центр/фуллскрин.
    # "confirm": (460, 500, 620, 560),
}

# Пути до шаблонов через серверный resolver (см. core/servers/l2mad/templates/resolver.py)
TEMPLATES: Dict[str, List[str]] = {
    "death_banner": ["death", "to_village_button.png"],  # при надобности заменить на реальный баннер
    "to_village":   ["death", "to_village_button.png"],
    # "confirm":    ["death", "confirm.png"],  # добавишь при наличии
}
