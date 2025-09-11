from __future__ import annotations
from typing import Any, Dict, Optional, Tuple, Callable

from core.state.pool import pool_get, pool_merge, pool_write
from core.orchestrators.snapshot import Snapshot
from core.engines.autofarm.runner import run_autofarm

# необязательная очередность (если есть helper очереди)
try:
    from core.state.helpers.queue import feature_slot  # type: ignore
except Exception:  # мягкий фолбэк
    from contextlib import contextmanager
    @contextmanager
    def feature_slot(*_args, **_kwargs):
        yield


def _normalize_cfg(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализация конфига: base = features.autofarm.config,
    поверх — непустые top-level ключи (profession/skills/zone/monsters/mode).
    """
    raw = dict(pool_get(state, "features.autofarm", {}) or {})
    base = dict(raw.get("config") or {})
    for k in ("profession", "skills", "zone", "monsters", "mode"):
        v = raw.get(k, None)
        if v not in (None, "", [], {}):
            base[k] = v
    return base


def _is_focused_now(
    *,
    state: Dict[str, Any],
    ps_adapter,
    snap: Snapshot,
) -> Optional[bool]:
    """
    Свежий фокус берём по приоритету:
    1) ps_adapter.last()['focus']['is_focused'] — источник с таймстампом
    2) pool: focus.is_focused
    3) исходный snap.is_focused
    Может вернуть None (неизвестно).
    """
    try:
        st = ps_adapter.last() or {}
        foc = st.get("focus") or {}
        v = foc.get("is_focused", None)
        if isinstance(v, bool):
            return v
    except Exception:
        pass

    v = pool_get(state, "focus.is_focused", None)
    if isinstance(v, bool):
        return v

    return snap.is_focused


def run_step(
    *,
    state: Dict[str, Any],
    ps_adapter,
    controller,
    report: Callable[[str], None],
    snap: Snapshot,
    helpers: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, bool]:
    """
    Шаг пайплайна AUTOFARM. Контракт: (ok, advance).

    Здесь ТОЛЬКО сценарная логика:
      - уважаем выключатель, фокус и факт жизни
      - manual → пропуск
      - auto → "пинаем" сервис, иначе fallback на однократный прогон движка
      - статусы/флаги features.autofarm.status/busy/waiting
    Весь низкоуровневый цикл — в server/boh/engine.py (через run_autofarm).
    """
    helpers = helpers or {}

    # выключено?
    if not bool(pool_get(state, "features.autofarm.enabled", False)):
        report("[AUTOFARM] выключено — пропуск шага")
        return True, True

    # окно есть?
    if not snap.has_window:
        report("[AUTOFARM] нет окна — пропуск")
        return False, False

    # жив ли игрок?
    alive = pool_get(state, "player.alive", None)
    if alive is False:
        report("[AUTOFARM] персонаж мёртв — пропуск (до респавна)")
        return True, True

    # уважение фокуса: если его нет — НЕ идём дальше, не тратим кулдаун
    focused = _is_focused_now(state=state, ps_adapter=ps_adapter, snap=snap)
    if focused is False:
        pool_merge(state, "features.autofarm", {"waiting": True, "status": "unfocused"})
        report("[AUTOFARM] пауза: окно без фокуса — жду")
        return False, False
    pool_merge(state, "features.autofarm", {"waiting": False})

    # режим
    cfg = _normalize_cfg(state)
    mode = (cfg.get("mode") or "auto").strip().lower()

    if mode == "manual":
        report("[AUTOFARM] режим manual — пропуск в пайплайне")
        return True, True

    # сначала даём шанс сервису (если подключён)
    try:
        svc = (state.get("_services") or {}).get("autofarm")
        if hasattr(svc, "run_once_now"):
            svc.run_once_now()
            pool_merge(state, "features.autofarm", {"status": "kicked"})
            report("[AUTOFARM] запуск цикла передан сервису")
            return True, True
    except Exception as e:
        report(f"[AUTOFARM] сервис недоступен, fallback: {e}")

    # fallback: одноразовый прогон движка (с уважением флагов)
    def _status(text: str, ok: Optional[bool] = None):
        report(f"[AUTOFARM] {text}")
        pool_merge(state, "features.autofarm", {"status": text or ""})

    # should_abort: выключили, потеряли фокус или умерли
    def _should_abort() -> bool:
        if not bool(pool_get(state, "features.autofarm.enabled", False)):
            return True
        f = _is_focused_now(state=state, ps_adapter=ps_adapter, snap=snap)
        if f is False:
            return True
        a = pool_get(state, "player.alive", None)
        if a is False:
            return True
        return False

    server = (pool_get(state, "config.server", "") or "").lower()

    # очередь/слот функции (если есть helper)
    with feature_slot(state, "autofarm", report, wait_key="features.autofarm", wait_msg="[AUTOFARM] очередь: жду слота"):
        # «busy» только на время фолбэка
        try:
            pool_write(state, "features.autofarm", {"busy": True})
        except Exception:
            pass
        try:
            ok = run_autofarm(
                server=server,
                controller=controller,
                get_window=lambda: pool_get(state, "window.info", None),
                get_language=lambda: pool_get(state, "config.language", "rus"),
                on_status=_status,
                cfg=cfg,
                should_abort=_should_abort,
            )
            return (bool(ok), True if ok else True)  # при ошибке не зацикливаем шаг
        finally:
            try:
                pool_write(state, "features.autofarm", {"busy": False})
            except Exception:
                pass
