# _archive/servers/boh/flows/rows/Goddard/VarkaSilenosStronghold/Varka_1.py
FLOW = [
    # примеры шагов; подставь свои шаблоны/клавиши
    {"op": "sleep", "ms": 1000},
    {"op": "send_message", "text": "/target Grazing Antelope", "delay_ms": 200},
    {"op": "sleep", "ms": 5000},
    # {"op": "send_arduino", "cmd": "wheel_click", "delay_ms": 300},  # повернуть
    # {"op": "sleep", "ms": 900},
    # {"op": "send_arduino", "cmd": "wheel_up", "delay_ms": 12, "count": 85},  #
    # {"op": "wait", "zone": "fullscreen", "tpl": "Varka_1_capt1", "timeout_ms": 2000, "thr": 0.87, "retry_count": 1, "retry_delay_ms": 1000, "retry_action": "prev"},
    # {"op": "sleep", "ms": 1500},
    # {"op": "click_in", "zone": "fullscreen", "tpl": "Varka_1_capt1", "timeout_ms": 2000, "thr": 0.87},
    # {"op": "sleep", "ms": 900},
    # {"op": "click_in", "zone": "fullscreen", "tpl": "autofarm", "timeout_ms": 1000, "thr": 0.87},
    # {"op": "sleep", "ms": 500},
    # {"op": "click_in", "zone": "fullscreen", "tpl": "autofarm", "timeout_ms": 1000, "thr": 0.87},


    # {"op": "send_arduino", "cmd": "pageup", "delay_ms": 300},
    # {"op": "sleep", "ms": 2000},
    # {"op": "wait", "zone": "center_block", "tpl": "landmark_bridge", "timeout_ms": 6000, "thr": 0.88},
    #     {"op": "send_arduino", "cmd": "pagedown", "delay_ms": 300},  #
    #     {"op": "sleep", "ms": 2000},
]
