# _archive/servers/l2mad/flows/buff_dashboard.py
FLOW = [
    {"op": "send_arduino", "cmd": "b"},
    {"op": "wait", "zone": "fullscreen", "teleportl": "dashboard_init", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 5, "retry_delay_ms": 1000, "retry_action": "prev"},
    {"op": "sleep", "ms": 900},
    {"op": "click_in", "zone": "fullscreen", "teleportl": "buffer_button", "timeout_ms": 12500, "thr": 0.87},
    {"op": "wait", "zone": "fullscreen", "teleportl": "buffer_init", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 5, "retry_delay_ms": 1000, "retry_action": "prev"},
    {"op": "sleep", "ms": 900},
    {"op": "click_in", "zone": "fullscreen", "teleportl": "{mode_key}", "timeout_ms": 2500, "thr": 0.88},
    {"op": "sleep", "ms": 900},
    {"op": "click_optional", "zone": "fullscreen", "teleportl": "buffer_restore_hp", "timeout_ms": 2500, "thr": 0.87},
    {"op": "sleep", "ms": 900},
    {"op": "send_arduino", "cmd": "b"},
]
