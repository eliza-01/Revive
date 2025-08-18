# core/servers/euro-pvp/zones/tp.py
# Зоны и последовательности для ТП: dashboard | gatekeeper
from typing import Dict, Tuple, List

ZONES: Dict[str, Tuple[int, int, int, int]] = {
    "dashboard_tab": (10, 10, 240, 120),
    "dashboard_tp": (250, 120, 950, 700),
    "gk_dialog": (220, 140, 900, 680),
    "confirm": (460, 500, 620, 560),
}

TEMPLATES = {
    "tab_tp": "l2mad/tab_tp",
    "tp_category": "l2mad/tp_category",   # общий префикс; конкретику обеспечит твой матчинг по id
    "tp_location": "l2mad/tp_location",
    "gk_category": "l2mad/gk_category",
    "gk_location": "l2mad/gk_location",
    "confirm": "common/btn_confirm",
}

SEQUENCE: Dict[str, List[tuple]] = {
    "dashboard": [
        ("key", "b"),
        ("click_template", "dashboard_tab", "tab_tp", 1500),
        # дальше выбор категории/локации делается программно
        ("click_dynamic", "dashboard_tp", "tp_category"),
        ("click_dynamic", "dashboard_tp", "tp_location"),
        ("click_template", "confirm", "confirm", 2000),
    ],
    "gatekeeper": [
        ("click_dynamic", "gk_dialog", "gk_category"),
        ("click_dynamic", "gk_dialog", "gk_location"),
        ("click_template", "confirm", "confirm", 2000),
    ],
}
