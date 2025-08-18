# core/servers/l2mad/flows/restart.py
# core/servers/l2mad/flows/restart.py

FLOW = [
    {  #1
        "op": "click_in", "zone": "settings_block", "tpl": "settings_button", "thr": 0.87,
        "timeout_ms": 4000,
        "retry_count": 3, "retry_delay_ms": 1000,
    },
    {  #2
        "op": "wait", "zone": "settings_block", "tpl": "restart_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 600,
    },

    {  #3
        "op": "click_in", "zone": "settings_block", "tpl": "restart_button", "thr": 0.87,
        "timeout_ms": 4000,
    },
    {  #4
        "op": "wait", "zone": "fullscreen", "tpl": "apply_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 600,
    },

    {  #5
        "op": "click_in", "zone": "fullscreen", "tpl": "apply_button", "thr": 0.87,
        "timeout_ms": 4000,
        "wait_ms": 3000,
    },

    # { "op": "sleep", "ms": 500 },  #6 (костыль против wait prev)

    {  #7
        "op": "wait", "zone": "settings_block", "tpl": "relogin_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 600,
    },
    {  #8
        "op": "click_in", "zone": "settings_block", "tpl": "relogin_button", "thr": 0.87,
        "timeout_ms": 4000, "retry_count": 3,
        "wait_ms": 2000,
    },
    {  #9
        "op": "wait", "zone": "fullscreen", "tpl": "enterGame_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 600,
    },

    #10
    { "op": "send_arduino", "cmd": "backspace_click", "delay_ms": 12, "count": 30},
    #11
    { "op": "send_message", "text": "IDtest0000", "layout": "en" },
    #12 Tab
    { "op": "send_arduino", "cmd": "t", "delay_ms": 1500 },
    #13
    { "op": "send_arduino", "cmd": "backspace_click", "delay_ms": 12, "count": 30},

    {  #14
        "op": "send_message", "text": "35595621", "layout": "en",
        "wait_ms": 1000,
    },

    {  #15
        "op": "click_in", "zone": "fullscreen", "tpl": "enterGame_button", "thr": 0.87,
        "timeout_ms": 4000, "retry_count": 3,
    },
    {  #16
        "op": "wait", "zone": "fullscreen", "tpl": "login_accept_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 1000,
    },
    {  #17
        "op": "click_in", "zone": "fullscreen", "tpl": "login_accept_button", "thr": 0.87,
        "timeout_ms": 4000, "retry_count": 3,
        "wait_ms": 600,
    },
    {  #18
        "op": "wait", "zone": "fullscreen", "tpl": "enterServerOk_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 1000,
    },
    {  #19
        "op": "click_in", "zone": "fullscreen", "tpl": "enterServerOk_button", "thr": 0.87,
        "timeout_ms": 4000, "retry_count": 3,
        "wait_ms": 600,
    },
    {  #20
        "op": "wait", "zone": "fullscreen", "tpl": "start_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 1000,
    },

    {  #21
        "op": "click_in", "zone": "fullscreen", "tpl": "start_button", "thr": 0.87,
        "timeout_ms": 4000,
        "wait_ms": 4000,
    },

    {  #22
        "op": "optional_click", "zone": "fullscreen", "tpl": "closeCross_button", "timeout_ms": 1500, "thr": 0.87,
        "wait_ms": 1000,
    },

    {  #23
        "op": "wait", "zone": "settings_block", "tpl": "settings_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
    },
]
