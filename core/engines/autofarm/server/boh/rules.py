from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

from core.state.pool import pool_get, pool_merge
from core.orchestrators.snapshot import Snapshot
from core.engines.autofarm.runner import run_autofarm


def run_step(
    *,
    state: Dict[str, Any],
    ps_adapter,
    controller,
    report,
    snap: Snapshot,
    helpers: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, bool]:
    """
    Шаг пайплайна AUTOFARM. Контракт: (ok, advance).
    """
    enabled = bool(pool_get(state, "features.autofarm.enabled", False))
    if not enabled:
        report("[AUTOFARM] выключено — пропуск шага")
        return True, True

    # --- нормализация конфига (как в сервисе): base = config, поверх непустые top-ключи
    raw = dict(pool_get(state, "features.autofarm", {}) or {})
    base = dict(raw.get("config") or {})
    for k in ("profession", "skills", "zone", "monsters", "mode"):
        v = raw.get(k, None)
        if v not in (None, "", [], {}):
            base[k] = v
    cfg = base
    mode = (cfg.get("mode") or "auto").strip().lower()

    # manual — пропуск в пайплайне; запускается пользователем вручную
    if mode == "manual":
        report("[AUTOFARM] режим manual — пропуск в пайплайне")
        return True, True

    # auto: попробовать «пнуть» сервис и выйти
    try:
        svc = (state.get("_services") or {}).get("autofarm")
        if hasattr(svc, "run_once_now"):
            svc.run_once_now()
            report("[AUTOFARM] запуск цикла передан сервису")
            return True, True
    except Exception as e:
        report(f"[AUTOFARM] сервис недоступен, fallback: {e}")

    # fallback — одноразовый прогон без сервиса (уважаем выключатель)
    def _status(text: str, ok: Optional[bool] = None):
        report(f"[AUTOFARM] {text}")
        pool_merge(state, "features.autofarm", {"status": text})

    srv = (pool_get(state, "config.server", "") or "").lower()
    ok = run_autofarm(
        server=srv,
        controller=controller,
        get_window=lambda: pool_get(state, "window.info", None),
        get_language=lambda: pool_get(state, "config.language", "rus"),
        on_status=_status,
        cfg=cfg,
        should_abort=lambda: (not pool_get(state, "features.autofarm.enabled", False)),
    )
    return (bool(ok), bool(ok))
