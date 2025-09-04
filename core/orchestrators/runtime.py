# core/orchestrators/runtime.py
from core.orchestrators.snapshot import build_snapshot

def orchestrator_tick(sys_state, watcher, rules):
    snap = build_snapshot(sys_state, watcher)
    for rule in rules:
        try:
            if rule.when(snap):
                rule.run(snap)
        except Exception as e:
            # не заваливать цикл, просто лог
            print(f"[orch] rule {rule.__class__.__name__} error:", e)
