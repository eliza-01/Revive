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
        "retry_count": 4, "retry_delay_ms": 2000, "retry_action": "prev",
        "wait_ms": 1000,
    },
    {  #4
        "op": "wait", "zone": "fullscreen", "tpl": "apply_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 4, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 1000,
    },


    {  #5
        "op": "click_in", "zone": "fullscreen", "tpl": "apply_button", "thr": 0.87,
        "timeout_ms": 4000,
        "retry_count": 4, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 3000,
    },
    #проверяемся на дисконнект
    {  #6
        "op": "wait_optional", "zone": "fullscreen", "tpl": "disconnect_window", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 4, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 1000,
    },
    {  # Да на Disconnect
        "op": "click_optional",
        "zone": "fullscreen",
        "tpl": "yes_button",
        "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 4, "retry_delay_ms": 2000, "retry_action": "prev",
        "wait_ms": 3000,
    },

    {  #7
        "op": "wait_optional", "zone": "settings_block", "tpl": "account_characters_init", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 600,
    },

    {  #8
        "op": "click_optional", "zone": "settings_block", "tpl": "relogin_button", "thr": 0.87,
        "timeout_ms": 4000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
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
    { "op": "send_message", "text": "{account_login}", "layout": "en" },
    #12 Tab
    { "op": "send_arduino", "cmd": "t", "delay_ms": 1500 },
    #13
    { "op": "send_arduino", "cmd": "backspace_click", "delay_ms": 12, "count": 30},

    { "op": "send_message", "text": "{account_password}", "layout": "en", "wait_ms": 1000 },


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
        "op": "wait", "zone": "fullscreen", "tpl": "account_characters_init", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 1000,
    },


    # Зашли в выбор персонажа wait_optional - ожидание с положительным результатом (ок) при всех провалах
    {  #20
        "op": "wait_optional", "zone": "fullscreen", "tpl": "pincode_init", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 1000,
    },
    {
        "op": "enter_pincode",
        "zone": "fullscreen",
        "digit_delay_ms": 120,
        "timeout_ms": 1500,
        "wait_ms": 600,
        # опционально можно подсказать какой tpl считать «признаком» панели:
        # "visible_tpl": "enter_pincode",
    },

    {  # подтверждение PIN — мягко (если кнопки нет, шаг всегда OK)
        "op": "click_optional",
        "zone": "fullscreen",
        "tpl": "enter_pincode",
        "timeout_ms": 1500,
        "thr": 0.87,
        "wait_ms": 300,
    },


        #тут снова ветвимся. Может быть ввод пинкода аккаунта.
        #ждем pincode_init. Если да - вводим pin если нет - просто старт


    {  #21
        "op": "click_in", "zone": "fullscreen", "tpl": "start_button", "thr": 0.87,
        "timeout_ms": 4000,
        "wait_ms": 4000,
    },

    {  #20
        "op": "wait", "zone": "settings_block", "tpl": "settings_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
        "wait_ms": 1000,
    },

    {  #22
        "op": "click_optional", "zone": "fullscreen", "tpl": "closeCross_button", "timeout_ms": 1500, "thr": 0.87,
        "wait_ms": 1000,
    },

    {  #23
        "op": "wait", "zone": "settings_block", "tpl": "settings_button", "thr": 0.87,
        "timeout_ms": 2000,
        "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev",
    },
]
