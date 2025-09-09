# core/orchestrators/runtime.py
from __future__ import annotations
import json
from typing import Any, Dict

from core.orchestrators.snapshot import build_snapshot
from core.state.pool import pool_get


def _json_sanitize(x):
    """
    Преобразует произвольный объект к JSON-безопасному виду.
    - dict/list/tuple обходятся рекурсивно
    - скаляры оставляем как есть
    - всё остальное -> "<ClassName>"
    """
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    if isinstance(x, dict):
        return {k: _json_sanitize(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_sanitize(v) for v in x]
    return f"<{x.__class__.__name__}>"


def _dump_pool(state: Dict[str, Any]) -> None:
    st = state.get("_state")
    if not st:
        return
    try:
        # компактный лог: чуть округлим float'ы
        def _round_numbers(v):
            if isinstance(v, float):
                return round(v, 3)
            if isinstance(v, dict):
                return {k: _round_numbers(v2) for k, v2 in v.items()}
            if isinstance(v, list):
                return [_round_numbers(x) for x in v]
            return v

        data = _json_sanitize(_round_numbers(st))
        print("----------------------------------------")
        print("[POOL]", json.dumps(data, ensure_ascii=False, sort_keys=True))
        print("----------------------------------------")
    except Exception as e:
        print("[POOL] dump error:", e)


def orchestrator_tick(state: Dict[str, Any], ps_adapter, rules) -> None:
    """
    Единственная точка входа тиков оркестратора.
    state — контейнер с _state (единый пул). Ничего не читаем из legacy-полей.
    """
    snap = build_snapshot(state, ps_adapter)

    # включаем дамп по флагу из пула
    if pool_get(state, "runtime.debug.pool_debug", False):
        _dump_pool(state)

    for rule in rules:
        if rule.when(snap):
            rule.run(snap)
