# core/runtime/flow_config.py
PRIORITY = [
    "buff_if_needed",   # если включён баф и не charged → баф
    "recheck_charged",  # пересчитать charged
    "tp_if_ready",      # если включён ТП и charged → ТП
]
