# core/engines/autofarm/server/l2mad/engine.py
from __future__ import annotations
from typing import Dict, Any
from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """
    Пример простейшего движка: клик по кнопке "autofarm" (фуллскрин темплейт).
    Конкретная логика — серверная; раннер её не знает.
    """
    zones = {"fullscreen": {"fullscreen": True}}

    fctx = FlowCtx(
        server=ctx_base["server"],
        controller=ctx_base["controller"],
        get_window=ctx_base["get_window"],
        get_language=ctx_base["get_language"],
        zones=zones,
        templates={},   # parts напрямую в flow
        extras={},
    )
    # Новая сигнатура: только logger (по умолчанию console.log)
    execu = FlowOpExecutor(fctx)

    flow = [
        {"op": "wait",     "zone": "fullscreen", "tpl": ["interface","autofarm.png"],
         "timeout_ms": 2000, "thr": 0.87},
        {"op": "click_in", "zone": "fullscreen", "tpl": ["interface","autofarm.png"],
         "timeout_ms": 2000, "thr": 0.87},
    ]
    return bool(run_flow(flow, execu))
