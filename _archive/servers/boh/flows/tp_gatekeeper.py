# _archive/servers/boh/flows/tp_gatekeeper.py
# L2MAD teleport flow (gatekeeper) — временно повторяет dashboard.
# Замените шаги под реальные действия с GK.
FLOW = [
    {"op": "send_arduino", "cmd": "b"},
    {"op": "sleep", "ms": 900},
    {"op": "send_arduino", "cmd": "b"},
    {"op": "wait", "zone": "fullscreen", "tpl": "dashboard_init", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 5, "retry_delay_ms": 1000, "retry_action": "prev"},
    {"op": "sleep", "ms": 900},
    {"op": "click_in", "zone": "fullscreen", "tpl": "teleport_button", "timeout_ms": 2000, "thr": 0.87},
    {"op": "wait", "zone": "fullscreen", "tpl": "teleport_init", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 5, "retry_delay_ms": 1000, "retry_action": "prev"},
    {"op": "sleep", "ms": 900},
    {"op": "click_village", "zone": "fullscreen", "timeout_ms": 2000, "thr": 0.88},
    {"op": "sleep", "ms": 900},
    {"op": "click_location", "zone": "fullscreen", "timeout_ms": 2000, "thr": 0.88},
]
