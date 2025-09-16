# core/orchestrators/runtime.py
from __future__ import annotations
from typing import Any, Dict
import json

from core.orchestrators.snapshot import build_snapshot
from core.state.pool import pool_get, dump_pool


def log_pool_snapshot(state: Dict[str, Any]) -> None:
    """
    Консольный лог пула (для отладки). Не экспортируется в UI.
    """
    try:
        snap = dump_pool(state, compact=True)
        print("----------------------------------------")
        print("[POOL]", json.dumps(snap, ensure_ascii=False, sort_keys=True))
        print("----------------------------------------")
    except Exception as e:
        print("[POOL] dump error:", e)


def orchestrator_tick(state: Dict[str, Any], ps_adapter, rules) -> None:
    snap = build_snapshot(state, ps_adapter)

    if pool_get(state, "runtime.debug.pool_debug", False):
        log_pool_snapshot(state)

    for rule in rules:
        try:
            if rule.when(snap):
                try:
                    rule.run(snap)
                except Exception as e:
                    print("[ORCH] rule.run error:", e)
        except Exception as e:
            print("[ORCH] rule.when error:", e)
