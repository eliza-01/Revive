from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

from core.state.pool import pool_get, pool_merge
from core.orchestrators.snapshot import Snapshot
from core.logging import console


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
    snap: Snapshot,
    helpers: Optional[Dict[str, Any]] = None,
    report: Optional[object] = None,  # ← оставлен для совместимости вызова из PipelineRule, не используется
) -> Tuple[bool, bool]:
    """
    Шаг пайплайна AUTOFARM. Контракт: (ok, advance).

    Здесь ТОЛЬКО сценарная логика:
      - уважаем выключатель, фокус и факт жизни
      - manual → пропуск
      - auto → "пинаем" сервис (если есть)
      - статусы/флаги features.autofarm.status/waiting
    Никаких фолбэков на прямой движок.
    """
    helpers = helpers or {}

    # выключено?
    if not bool(pool_get(state, "features.autofarm.enabled", False)):
        console.hud("ok", "[AUTOFARM] выключено — пропуск шага")
        return True, True

    # окно есть?
    if not snap.has_window:
        console.hud("err", "[AUTOFARM] нет окна — пропуск")
        return False, False

    # жив ли игрок?
    alive = pool_get(state, "player.alive", None)
    if alive is False:
        console.hud("ok", "[AUTOFARM] персонаж мёртв — пропуск (до респавна)")
        return True, True

    # уважение фокуса: если его нет — НЕ идём дальше, не тратим кулдаун
    focused = _is_focused_now(state=state, ps_adapter=ps_adapter, snap=snap)
    if focused is False:
        pool_merge(state, "features.autofarm", {"waiting": True, "status": "unfocused"})
        console.hud("ok", "[AUTOFARM] пауза: окно без фокуса — жду")
        return False, False
    pool_merge(state, "features.autofarm", {"waiting": False})

    # режим
    cfg = _normalize_cfg(state)
    mode = (cfg.get("mode") or "auto").strip().lower()

    if mode == "manual":
        console.hud("ok", "[AUTOFARM] режим manual — пропуск в пайплайне")
        return True, True

    # auto: даём команду сервису (если подключён)
    try:
        svc = (state.get("_services") or {}).get("autofarm")
        if hasattr(svc, "run_once_now"):
            svc.run_once_now()
            pool_merge(state, "features.autofarm", {"status": "kicked"})
            console.hud("ok", "[AUTOFARM] запуск цикла передан сервису")
            return True, True
        else:
            console.hud("err", "[AUTOFARM] сервис не найден — пропуск шага")
            console.log("[AUTOFARM] service object missing or has no run_once_now()")
            return True, True
    except Exception as e:
        console.hud("err", "[AUTOFARM] ошибка обращения к сервису — пропуск шага")
        console.log(f"[AUTOFARM] service access error: {e}")
        return True, True
