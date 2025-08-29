# core/engines/autofarm/runner.py
from __future__ import annotations
import os, json
from typing import Callable, Dict, Any, List

AF_ROOT = os.path.dirname(__file__)

def _load_json(p: str) -> Any:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def _af_flow_path(server: str) -> str:
    # server/flows/af_click.json, иначе common/flows/af_click.json (если сделаешь)
    p = os.path.join(AF_ROOT, server, "flows", "af_click.json")
    if os.path.exists(p): return p
    return os.path.join(AF_ROOT, "common", "flows", "af_click.json")

def run_af_click_button(
    server: str,
    controller,
    get_window: Callable[[], Dict],
    get_language: Callable[[], str],
    on_status: Callable[[str, bool|None], None] = lambda *_: None,
) -> bool:
    from core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

    lang = (get_language() or "eng").lower()
    zones = {"fullscreen": {"fullscreen": True}}   # нам хватает фуллскрина
    templates: Dict[str, List[str]] = {}           # не нужны, т.к. в flow — parts-массивы

    ctx = FlowCtx(
        server=server,
        controller=controller,
        get_window=get_window,
        get_language=get_language,
        zones=zones,
        templates=templates,
        extras={}
    )
    ex = FlowOpExecutor(ctx, on_status, logger=lambda s: print(s))
    flow = _load_json(_af_flow_path(server))
    return bool(run_flow(flow, ex))
