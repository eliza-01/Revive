# core/engines/autofarm/runner.py
from __future__ import annotations
import os, json
from typing import Callable, Dict, Any, List

AF_ROOT = os.path.dirname(__file__)

def _load_json(p: str) -> Any:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def _af_flow_path(server: str) -> str:
    """
    Новый приоритет:
      1) core/engines/autofarm/server/<server>/flows/af_click.json
      2) core/engines/autofarm/server/common/flows/af_click.json (общий дефолт)
    Никаких legacy-путей.
    """
    p_srv = os.path.join(AF_ROOT, "server", server, "flows", "af_click.json")
    if os.path.exists(p_srv):
        return p_srv
    return os.path.join(AF_ROOT, "server", "common", "flows", "af_click.json")

def run_af_click_button(
    server: str,
    controller,
    get_window: Callable[[], Dict],
    get_language: Callable[[], str],
    on_status: Callable[[str, bool|None], None] = lambda *_: None,
) -> bool:
    from core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

    zones = {"fullscreen": {"fullscreen": True}}
    templates: Dict[str, List[str]] = {}

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
