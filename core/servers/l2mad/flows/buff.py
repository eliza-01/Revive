# core/servers/l2mad/flows/buff.py
# Цикл автобафa для L2MAD. Зонные ключи и template-ключи берутся из zones/buff.py
# Доступные действия:
#   - {"op":"click_any", "zones":["dashboard_tab","dashboard_body"], "tpl":"buffer_button", "timeout_ms":2000, "thr":0.87}
#   - {"op":"wait", "zone":"dashboard_body", "tpl":"buffer_init", "timeout_ms":2000, "thr":0.87}
#   - {"op":"click_in", "zone":"dashboard_body", "tpl":"<mode_key>", "timeout_ms":2500, "thr":0.88}
#   - {"op":"sleep", "ms":100}
#   - {"op":"optional_click", "zone":"dashboard_body", "tpl":"buffer_restore_hp", "timeout_ms":1000, "thr":0.87}
FLOW = [
    {"op": "send_arduino", "cmd": "b"},  # Открыть дэшборд
    {"op": "sleep",     "ms": 700},
    {"op": "wait", "zone": "dashboard_body", "tpl": "dashboard_init", "timeout_ms": 1000, "thr": 0.87},
    {"op": "click_in", "zone": "dashboard_body", "tpl": "buffer_button", "timeout_ms": 1000, "thr": 0.87},
    {"op": "wait",      "zone": "dashboard_body", "tpl": "buffer_init",   "timeout_ms": 1000, "thr": 0.87},
    # {"op": "dashboard_is_locked", "zone": "dashboard_body", "tpl": "dashboard_blocked", "timeout_ms": 10000, "thr": 0.87},
    {"op": "click_in",  "zone": "dashboard_body", "tpl": "{mode_key}",    "timeout_ms": 2500, "thr": 0.88},
    {"op": "sleep",     "ms": 1000},
    {"op": "optional_click", "zone": "dashboard_body", "tpl": "buffer_restore_hp", "timeout_ms": 1000, "thr": 0.87},
    {"op": "sleep",     "ms": 700},
    {"op": "send_arduino", "cmd": "b"},  # Закрыть дэшборд
]
