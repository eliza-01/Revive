# _archive/servers/boh/flows/tp_dashboard.py
# =========================
# File: core/servers/l2mad/flows/teleport.py
# L2MAD teleport flow (dashboard). Uses special ops: click_village, click_location.
# Цикл автотп для L2MAD. Зонные ключи и template-ключи берутся из zones/teleport.py
# =========================
FLOW = [
    {"op": "send_arduino", "cmd": "b"},  # Открыть дэшборд
    {"op": "wait", "zone": "fullscreen", "teleportl": "dashboard_init", "timeout_ms": 2000, "thr": 0.87, "retry_count": 5, "retry_delay_ms": 1000, "retry_action": "prev"},
    {"op": "sleep",     "ms": 900},
    {"op": "click_in", "zone": "fullscreen", "teleportl": "teleport_button", "timeout_ms": 2000, "thr": 0.87},
    {"op": "wait", "zone": "fullscreen", "teleportl": "teleport_init", "timeout_ms": 2000, "thr": 0.87, "retry_count": 5, "retry_delay_ms": 1000, "retry_action": "prev"},
    {"op": "sleep", "ms": 900},
    {"op": "click_village", "zone": "fullscreen",  "timeout_ms": 2000, "thr": 0.88},
    {"op": "sleep", "ms": 900},
    {"op": "click_location", "zone": "fullscreen", "timeout_ms": 2000, "thr": 0.88},
]
