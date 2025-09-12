from __future__ import annotations
import time
from typing import Any, Dict, Optional, Tuple, List

from core.state.pool import pool_get, pool_write
from core.orchestrators.snapshot import Snapshot
from core.logging import console


def run_step(
    *,
    state: Dict[str, Any],
    ps_adapter,
    controller,
    snap: Snapshot,
    helpers: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, bool]:
    """
    Правило шага RESPawn для текущего сервера. Контракт: (ok, advance).

    Сценарий:
      - если нет фокуса — не тикаем (ожидание)
      - при ожидании ищем ТОЛЬКО reborn_banner/accept_button
      - по таймауту: если виден reborn → revive, иначе → self (death)
      - фиксируем features.respawn.last_respawn.type и бампим макросы
    """
    helpers = helpers or {}

    def _focused_now() -> Optional[bool]:
        try:
            v = pool_get(state, "focus.is_focused", None)
            return bool(v) if isinstance(v, bool) else None
        except Exception:
            return None

    # окно и фокус
    if not snap.has_window:
        return False, False

    # уважение фокуса — время не тратим
    if _focused_now() is False:
        console.hud("ok", "[RESPAWN] пауза: окно без фокуса — жду")
        return False, False

    # уже жив — ничего не делаем
    if snap.alive is True:
        _reset_macros_after_respawn(state)
        return True, True

    # движок
    runner = helpers.get("respawn_runner")
    if runner is None or not hasattr(runner, "engine"):
        console.log("[RESPAWN] internal: runner/engine missing")
        return False, True
    engine = runner.engine

    get_window = helpers.get("get_window") or (lambda: None)
    get_language = helpers.get("get_language") or (lambda: "rus")
    win = get_window() or {}
    lang = (get_language() or "rus").lower()

    # busy — чтобы фокус-правило могло корректно возобновляться
    try:
        pool_write(state, "features.respawn", {"busy": True})
    except Exception:
        pass

    try:
        wait_enabled = bool(pool_get(state, "features.respawn.wait_enabled", False))
        wait_seconds = int(pool_get(state, "features.respawn.wait_seconds", 0))

        if wait_enabled and wait_seconds > 0:
            console.hud("ok", f"[RESPAWN] жду reborn_banner {wait_seconds} сек")
            elapsed_focused = 0.0  # считаем только «в фокусе»
            last_ts = time.time()

            last_tick = -1
            while elapsed_focused < wait_seconds:
                now = time.time()
                dt = now - last_ts
                last_ts = now

                # ожили сами — считаем revive
                st = ps_adapter.last() or {}
                if st.get("alive"):
                    _set_last_respawn(state, "revive")
                    console.hud("succ", "[RESPAWN] ожили во время ожидания (revive)")
                    _reset_macros_after_respawn(state)
                    return True, True

                # без фокуса — время не идёт
                if _focused_now() is False:
                    tick = int(elapsed_focused)
                    if tick != last_tick:
                        last_tick = tick
                        console.log(f"[RESPAWN] unfocused, waiting… {tick}/{wait_seconds}s")
                    time.sleep(0.2)
                    continue

                # с фокусом — тикаем и сканим только reborn
                elapsed_focused = min(wait_seconds, elapsed_focused + dt)
                tick = int(elapsed_focused)
                if tick != last_tick:
                    last_tick = tick
                    console.log(f"[RESPAWN] ожидание reborn… {tick}/{wait_seconds}s")

                found = engine.scan_banner_key(
                    win, lang,
                    allowed_keys=["reborn_banner", "accept_button"]
                )
                if found and found[1] in ("reborn_banner", "accept_button"):
                    console.hud("ok", "[RESPAWN] найден reborn — поднимаюсь (accept)")
                    ok = bool(engine.run_stand_up_once(
                        win, lang, timeout_ms=14_000,
                        allowed_keys=["reborn_banner", "accept_button"]
                    ))
                    if ok:
                        _set_last_respawn(state, "revive")
                        console.hud("succ", "[RESPAWN] итог: type=revive")
                        _reset_macros_after_respawn(state)
                        return True, True
                    else:
                        console.hud("err", "[RESPAWN] reborn не сработал — повтор шага")
                        return False, False

                time.sleep(0.2)

            # таймаут ожидания
            console.hud("ok", "[RESPAWN] таймер ожидания вышел")
            prefer_reborn = engine.scan_banner_key(
                win, lang,
                allowed_keys=["reborn_banner", "accept_button"]
            )
            if prefer_reborn and prefer_reborn[1] in ("reborn_banner", "accept_button"):
                console.hud("ok", "[RESPAWN] по таймауту: reborn виден — поднимаюсь (accept)")
                ok = bool(engine.run_stand_up_once(
                    win, lang, timeout_ms=14_000,
                    allowed_keys=["reborn_banner", "accept_button"]
                ))
                rtype = "revive"
            else:
                console.hud("ok", "[RESPAWN] по таймауту: reborn нет — поднимаюсь сам (death)")
                ok = bool(engine.run_stand_up_once(
                    win, lang, timeout_ms=14_000,
                    allowed_keys=["death_banner"]
                ))
                rtype = "self"

            if ok:
                _set_last_respawn(state, rtype)
                console.hud("succ", f"[RESPAWN] итог: type={rtype}")
                _reset_macros_after_respawn(state)
                return True, True
            return False, True

        # --- Без ожидания: пробуем reborn, иначе death ---
        found = engine.scan_banner_key(
            win, lang,
            allowed_keys=["reborn_banner", "accept_button", "death_banner"]
        )
        if found and found[1] in ("reborn_banner", "accept_button"):
            console.hud("ok", "[RESPAWN] auto: найден reborn — поднимаюсь (accept)")
            ok = bool(engine.run_stand_up_once(
                win, lang, timeout_ms=14_000,
                allowed_keys=["reborn_banner", "accept_button"]
            ))
            rtype = "revive"
        elif found and found[1] == "death_banner":
            console.hud("ok", "[RESPAWN] auto: найден death — поднимаюсь сам")
            ok = bool(engine.run_stand_up_once(
                win, lang, timeout_ms=14_000,
                allowed_keys=["death_banner"]
            ))
            rtype = "self"
        else:
            console.hud("ok", "[RESPAWN] auto: баннеры не видны — общий подъём")
            ok = bool(engine.run_stand_up_once(
                win, lang, timeout_ms=14_000,
                allowed_keys=["reborn_banner", "accept_button", "death_banner"]
            ))
            rtype = "self"

        if ok:
            _set_last_respawn(state, rtype)
            console.hud("succ", f"[RESPAWN] итог: type={rtype}")
            _reset_macros_after_respawn(state)
            return True, True

        return False, True

    finally:
        try:
            pool_write(state, "features.respawn", {"busy": False})
        except Exception:
            pass


# ---- utils ----

def _set_last_respawn(state: Dict[str, Any], rtype: str) -> None:
    try:
        if rtype in ("revive", "self"):
            pool_write(state, "features.respawn", {"last_respawn": {"type": rtype}})
    except Exception:
        pass


def _reset_macros_after_respawn(state: Dict[str, Any]) -> None:
    try:
        svc = (state.get("_services") or {}).get("macros_repeat")
        if hasattr(svc, "bump_all"):
            svc.bump_all()
    except Exception:
        pass
