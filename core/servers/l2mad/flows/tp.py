# =========================
# File: core/servers/l2mad/flows/tp.py
# L2MAD teleport flow (dashboard). Uses special ops: click_village, click_location.
# =========================
FLOW = [
    {"op": "send_arduino", "cmd": "b"},                          # открыть дэшборд
    {"op": "sleep", "ms": 9000},
    # {"op": "wait", "zone": "dashboard_body", "tpl": "dashboard_init", "timeout_ms": 1200, "thr": 0.87},

    # На всякий случай таб ТП может быть и в шапке, и в теле
    {"op": "click_in", "zone": "dashboard_body", "tpl": "teleport_button", "timeout_ms": 1500, "thr": 0.87},                   # открыть дэшборд
    {"op": "sleep", "ms": 1000},

    # Если панель была залочена боем — ждём разблокировки и повторяем клик по табу
    # {"op": "dashboard_is_locked", "zone": "dashboard_body", "tpl": "dashboard_blocked", "timeout_ms": 8000, "thr": 0.87},
    {"op": "click_in", "zone": "dashboard_body", "tpl": "teleport_button", "timeout_ms": 1500, "thr": 0.87},                   # открыть дэшборд
    {"op": "sleep", "ms": 1000},

    # Выбор деревни и точки
    {"op": "click_village",  "timeout_ms": 2500, "thr": 0.88},                # открыть дэшборд
    {"op": "sleep", "ms": 1000},
    {"op": "click_location", "timeout_ms": 2500, "thr": 0.88},                # открыть дэшборд
    {"op": "sleep", "ms": 1000},

    # Подтверждение (если есть шаблон confirm в zones.tp:TEMPLATES)
    # {"op": "optional_click", "zone": "confirm", "tpl": "confirm", "timeout_ms": 1500, "thr": 0.90},

#     {"op": "sleep", "ms": 300},
#     {"op": "send_arduino", "cmd": "b"},                          # закрыть дэшборд
]
