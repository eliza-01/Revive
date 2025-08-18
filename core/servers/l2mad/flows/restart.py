# core/servers/l2mad/flows/restart.py

FLOW = [
    {"op": "click_in", "zone": "settings_block", "tpl": "settings_button", "timeout_ms": 4000, "thr": 0.87},
    {"op": "wait", "zone": "settings_block", "tpl": "restart_button", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev", "wait_ms": 600},

    {"op": "click_in", "zone": "settings_block", "tpl": "restart_button", "timeout_ms": 4000, "thr": 0.87},
    {"op": "wait", "zone": "fullscreen", "tpl": "apply_button", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev", "wait_ms": 600},

    {"op": "click_in", "zone": "fullscreen", "tpl": "apply_button", "timeout_ms": 4000, "thr": 0.87},
    {"op": "wait", "zone": "settings_block", "tpl": "relogin_button", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev", "wait_ms": 600},

    {"op": "click_in", "zone": "settings_block", "tpl": "relogin_button",
     "retry_count": 3, "timeout_ms": 4000, "thr": 0.87},
    {"op": "wait", "zone": "fullscreen", "tpl": "enterGame_button", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev", "wait_ms": 600},

    {"op": "send_message", "text": "IDtest0000", "layout": "en"},
    {"op": "send_arduino", "cmd": "t", "delay_ms": 1500},  # Tab
    {"op": "send_message", "text": "35595621", "layout": "en"},
    {"op": "click_in", "zone": "fullscreen", "tpl": "enterGame_button", "timeout_ms": 4000, "thr": 0.87},

    {"op": "wait", "zone": "fullscreen", "tpl": "accept_button", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev", "wait_ms": 1000},

    {"op": "click_in", "zone": "fullscreen", "tpl": "accept_button", "timeout_ms": 4000, "thr": 0.87, "wait_ms": 600},
    {"op": "wait", "zone": "settings_block", "tpl": "start_button", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev", "wait_ms": 1000},

    {"op": "click_in", "zone": "fullscreen", "tpl": "start_button", "timeout_ms": 4000, "thr": 0.87},
    {"op": "wait", "zone": "settings_block", "tpl": "settings_button", "timeout_ms": 2000, "thr": 0.87,
     "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev"},
]
