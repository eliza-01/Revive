# core/orchestrators/runtime.py
import json
from core.orchestrators.snapshot import build_snapshot

def _dump_pool(sys_state):
    st = sys_state.get("_state")
    if not st:
        return
    try:
        # аккуратно округлим числа, чтобы лог был компактнее
        def _round(v):
            if isinstance(v, float):
                return round(v, 3)
            if isinstance(v, dict):
                return {k: _round(v2) for k, v2 in v.items()}
            if isinstance(v, list):
                return [_round(x) for x in v]
            return v
        data = _round(st)
        print("----------------------------------------")
        print("[POOL]", json.dumps(data, ensure_ascii=False, sort_keys=True))
        print("----------------------------------------")
    except Exception as e:
        print("[POOL] dump error:", e)

def orchestrator_tick(sys_state, ps_adapter, rules):
    snap = build_snapshot(sys_state, ps_adapter)

    # ⬇️ новый дамп пула
    if sys_state.get("pool_debug"):
        _dump_pool(sys_state)

    for rule in rules:
        if rule.when(snap):
            rule.run(snap)
