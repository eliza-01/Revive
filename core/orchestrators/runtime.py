# core/orchestrators/runtime.py
from core.orchestrators.snapshot import build_snapshot

def orchestrator_tick(sys_state, ps_adapter, rules):
    snap = build_snapshot(sys_state, ps_adapter)
    for rule in rules:
        if rule.when(snap):
            rule.run(snap)
