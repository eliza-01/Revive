# core/servers/l2mad/flows/rows/Rune/PrimevalIsle/Primeval_1.py
FLOW = [
    # примеры шагов; подставь свои шаблоны/клавиши
    {"op": "sleep", "ms": 2000},
    # { "op": "send_message", "text": "Привет гандоны", "layout": "ru" },
    # {"op": "sleep", "ms": 1000},
    # { "op": "set_layout", "layout": "ru" },

    # {"op": "sleep", "ms": 1000},
    # { "op": "set_layout", "layout": "toggle", "count": 2, "delay_ms": 150 }

    {"op": "send_arduino", "cmd": "pagedown", "delay_ms": 300},  # повернуть
    {"op": "sleep", "ms": 500},
    {"op": "send_arduino", "cmd": "pageup", "delay_ms": 300},  # повернуть
    {"op": "sleep", "ms": 500},
    { "op": "send_message", "text": "/target Vervato", "layout": "en" },
    {"op": "sleep", "ms": 500},
    { "op": "send_message", "text": "/attack", "layout": "en" },
    {"op": "sleep", "ms": 2000},
    { "op": "send_message", "text": "/target Donate Shop", "layout": "en" },
    {"op": "sleep", "ms": 500},
    { "op": "send_message", "text": "/attack", "layout": "en" },
    {"op": "sleep", "ms": 2000},
    { "op": "send_message", "text": "/sit", "layout": "en", "delay_ms": 1500, "wait_ms": 3000 },
    { "op": "send_message", "text": "/stand", "layout": "en", "delay_ms": 1500, "wait_ms": 1000 },
    {"op": "send_arduino", "cmd": "wheel_click", "delay_ms": 300},  # повернуть
    {"op": "sleep", "ms": 500},
    {"op": "send_arduino", "cmd": "r", "delay_ms": 300},  # повернуть
    # {"op": "sleep", "ms": 200},
    # {"op": "send_arduino", "cmd": "wheel_up", "delay_ms": 12, "count": 400},  #
    # {"op": "sleep", "ms": 1200},
    # # {"op": "click_in", "zone": "fullscreen", "tpl": "Primeval_1_capt1", "timeout_ms": 2000, "thr": 0.50},
    # {"op":"click_zone_center","zone":"Primeval_1_zone1","delay_ms":300},
    # #фэйлит потому что мы уже сдвинулись
    # # {"op": "wait", "zone": "fullscreen", "tpl": "Primeval_1_capt1", "timeout_ms": 2000, "thr": 0.87, "retry_count": 3, "retry_delay_ms": 1000, "retry_action": "prev"},
    # {"op": "sleep", "ms": 2000},
    # # без дубля не хочет идти
    # {"op": "send_arduino", "cmd": "l", "delay_ms": 300},  # повернуть
    # {"op": "sleep", "ms": 200},
    # {"op": "send_arduino", "cmd": "pagedown", "delay_ms": 300},  # повернуть
    # {"op": "sleep", "ms": 500},
    # {"op": "send_arduino", "cmd": "pageup", "delay_ms": 300},  # повернуть
    # {"op": "sleep", "ms": 21000},
    # {"op": "click_zone_center","zone":"left_ratio_50_top_ratio20","delay_ms":300},
    {"op": "sleep", "ms": 300},
    {"op": "send_arduino", "cmd": "l", "delay_ms": 300},  # клик на подтверждение
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
    #     {"op": "send_arduino", "cmd": "pagedown", "delay_ms": 300},  # повернуть
    #     {"op": "sleep", "ms": 2000},
]

# Английский/сырой текст (ничего не конвертировать):
# { "op": "send_message", "text": "Ready at spot.", "layout": "en" }
# или
# { "op": "send_message", "text": "Ready at spot.", "layout": "raw" }

# Русский (конвертация в US-клавиши под включённую RU-раскладку):
# { "op": "send_message", "text": "Привет! Я на месте.", "layout": "ru" }
