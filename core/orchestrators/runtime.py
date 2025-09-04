# core/orchestrators/runtime.py
# общий цикл, StateStore, SingleFlight, приоритеты, cooldown
from core.orchestrators.snapshot import build_snapshot

def orchestrator_tick(sys_state, watcher, rules):
    snap = build_snapshot(sys_state, watcher)
    for rule in rules:
        if rule.when(snap):
            rule.run(snap)
