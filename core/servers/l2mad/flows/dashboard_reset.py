# core/servers/l2mad/flows/dashboard_reset.py
FLOW = [
    # Если дэшборд открыт (виден dashboard_init) — жмём 'b', пока не исчезнет
    {"op": "while_visible_send", "zone": "dashboard_body", "tpl": "dashboard_init", "cmd": "b", "probe_interval_s": 1, "timeout_ms": 10000},
]
