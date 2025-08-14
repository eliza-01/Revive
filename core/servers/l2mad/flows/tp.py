# =========================
# File: core/servers/l2mad/flows/tp.py
# L2MAD teleport flow (dashboard). Uses special ops: click_village, click_location.
# =========================
FLOW = [
    {"op": "send_arduino", "cmd": "b"},
    {"op": "sleep", "ms": 900},
    {"op": "click_in", "zone": "dashboard_body", "tpl": "teleport_button", "timeout_ms": 2000, "thr": 0.87},
    {"op": "sleep", "ms": 900},
    {"op": "dashboard_is_locked", "zone": "dashboard_body", "tpl": "dashboard_is_locked", "timeout_ms": 12000, "thr": 0.80},
    {"op": "sleep", "ms": 900},
    {"op": "click_village",  "timeout_ms": 2000, "thr": 0.88},
    {"op": "sleep", "ms": 900},
    {"op": "click_location", "timeout_ms": 2000, "thr": 0.88},
    {"op": "optional_click", "zone": "confirm", "tpl": "confirm", "timeout_ms": 1500, "thr": 0.90, "retry_count": 1, "retry_action": "prev"},
    {"op": "sleep", "ms": 900},
    {"op": "dashboard_is_locked", "zone": "dashboard_body", "tpl": "dashboard_is_locked", "timeout_ms": 12000, "thr": 0.80},
]
