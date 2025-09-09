# core/orchestrators/runtime.py
from core.orchestrators.snapshot import build_snapshot

def orchestrator_tick(sys_state, ps_adapter, rules):
    snap = build_snapshot(sys_state, ps_adapter)

    # подробный, но лаконичный дамп тика (вкл, если надо)
    if sys_state.get("respawn_enabled"):
        hp = "?" if snap.hp_ratio is None else snap.hp_ratio
        alive = "?" if snap.alive is None else snap.alive
        print(
            f"[DBG] snap win={snap.has_window} focus={snap.has_focus} alive={alive} hp={hp} respawn={sys_state.get('respawn_enabled')}")
    for rule in rules:
        if rule.when(snap):
            rule.run(snap)
