# core/servers/boh/flows/buff.py
# =========================
# buff.py — оставь как «шлюз» (бэк-компат)

from .buff_dashboard import FLOW  # переиспользуем


# FLOW = [
#     {"op": "send_arduino", "cmd": "b"},  # Открыть дэшборд
#     {"op": "wait", "zone": "fullscreen", "tpl": "dashboard_init", "timeout_ms": 2000, "thr": 0.87, "retry_count": 5, "retry_delay_ms": 1000, "retry_action": "prev"},
#     {"op": "sleep",     "ms": 900},
#     {"op": "click_in", "zone": "fullscreen", "tpl": "buffer_button", "timeout_ms": 12500, "thr": 0.87},
#     {"op": "wait", "zone": "fullscreen", "tpl": "buffer_init", "timeout_ms": 2000, "thr": 0.87, "retry_count": 5, "retry_delay_ms": 1000, "retry_action": "prev"},
#     {"op": "sleep",     "ms": 900},
#     {"op": "click_in",  "zone": "fullscreen", "tpl": "{mode_key}",    "timeout_ms": 2500, "thr": 0.88},
#     {"op": "sleep",     "ms": 900},
#     {"op": "click_optional", "zone": "fullscreen", "tpl": "buffer_restore_hp", "timeout_ms": 2500, "thr": 0.87},
#     {"op": "sleep",     "ms": 900},
#     {"op": "send_arduino", "cmd": "b"},  # Закрыть дэшборд
# ]


# Доступные действия:
#   - {"op":"click_any", "zones":["dashboard_tab","dashboard_body"], "tpl":"buffer_button", "timeout_ms":2000, "thr":0.87}
#   - {"op":"wait", "zone":"dashboard_body", "tpl":"buffer_init", "timeout_ms":2000, "thr":0.87}
#   - {"op":"click_in", "zone":"dashboard_body", "tpl":"<mode_key>", "timeout_ms":2500, "thr":0.88}
#   - {"op":"sleep", "ms":100}
#   - {"op":"click_optional", "zone":"dashboard_body", "tpl":"buffer_restore_hp", "timeout_ms":1000, "thr":0.87}
#   - {"op": "dashboard_is_locked", "zone": "dashboard_body", "tpl": "dashboard_is_locked", "timeout_ms": 12000, "thr": 0.80}
