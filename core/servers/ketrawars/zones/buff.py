# core/servers/ketrawars/zones/buff.py
# Описывает зоны и последовательности для бафа. Две ветки: dashboard | npc
from typing import Dict, Tuple, List

ZONES: Dict[str, Tuple[int, int, int, int]] = {
    "dashboard_tab": (10, 10, 240, 120),
    "dashboard_body": (250, 120, 950, 700),
    "npc_dialog": (200, 150, 900, 650),
    "buff_panel": (260, 160, 940, 680),
}

TEMPLATES = {
    "tab_buffer": "l2mad/tab_buffer",
    "buffer_icon": "l2mad/buffer_icon",
    "npc_buffer": "l2mad/npc_buffer",
    "apply_buffs": "l2mad/btn_apply_buffs",
    "locked_in_combat": "l2mad/locked_in_combat",
    "close_dialog": "common/btn_close",
}

SEQUENCE: Dict[str, List[tuple]] = {
    "dashboard": [
        ("key", "b"),
        ("click_template", "dashboard_tab", "tab_buffer", 1500),
        ("wait_template", "buff_panel", "apply_buffs", 3000),
        ("click_template", "buff_panel", "apply_buffs", 2000),
        ("click_template", "buff_panel", "close_dialog", 1500),
    ],
    "npc": [
        ("click_template", "npc_dialog", "npc_buffer", 4000),
        ("wait_template", "buff_panel", "apply_buffs", 3000),
        ("click_template", "buff_panel", "apply_buffs", 2000),
        ("click_template", "buff_panel", "close_dialog", 1500),
    ],
}
