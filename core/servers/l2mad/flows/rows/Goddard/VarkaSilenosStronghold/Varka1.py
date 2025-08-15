# core/servers/l2mad/flows/rows/Goddard/VarkaSilenosStronghold/safe_route.py
FLOW = [
    # примеры шагов; подставь свои шаблоны/клавиши
    {"op": "send_arduino", "cmd": "pageup", "delay_ms": 300},
    {"op": "sleep", "ms": 2000},
    # {"op": "wait", "zone": "center_block", "tpl": "landmark_bridge", "timeout_ms": 6000, "thr": 0.88},
    {"op": "send_arduino", "cmd": "pagedown", "delay_ms": 300},  # повернуть
]
