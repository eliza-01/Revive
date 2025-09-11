from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import time

from core.state.pool import pool_get, pool_write
from core.orchestrators.snapshot import Snapshot


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
    Сценарий:
      - если нет фокуса — не тикаем
      - во время ожидания ищем ТОЛЬКО reborn_banner/accept_button
      - по таймауту: если видно reborn → revive, иначе → death (self)
      - HUD + запись features.respawn.last_respawn.type
    """
    helpers = helpers or {}

    def is_focused_now() -> bool:
        """Свежий фокус: сперва из ps_adapter, затем из пула, затем из снапшота."""
        # 1) свежайший источник — адаптер (его апдейтит WindowFocusService)
        try:
            val = pool_get(state, "focus.is_focused", None)
            if isinstance(val, bool):
                report(f"[RESPAWN] focus(pool) = {val}")
                return val
        except Exception:
            pass

    # окно и фокус
    if not snap.has_window:
        return False, False

    # перед любой активностью — уважение фокуса
    if is_focused_now() is False:
        report("[RESPAWN] пауза: окно без фокуса — жду возврата фокуса")
        return False, False

    # уже жив
    if snap.alive is True:
        _reset_macros_after_respawn(state)
        return True, True

    # движок
    runner = helpers.get("respawn_runner")
    if runner is None or not hasattr(runner, "engine"):
        report("[RESPAWN] internal: runner/engine missing")
        return False, True
    engine = runner.engine

    get_window = helpers.get("get_window") or (lambda: None)
    get_language = helpers.get("get_language") or (lambda: "rus")
    win = get_window() or {}
    lang = (get_language() or "rus").lower()

    # busy — чтобы unfocus-правило могло восстановиться
    try:
        pool_write(state, "features.respawn", {"busy": True})
    except Exception:
        pass

    try:
        wait_enabled = bool(pool_get(state, "features.respawn.wait_enabled", False))
        wait_seconds = int(pool_get(state, "features.respawn.wait_seconds", 0))

        if wait_enabled and wait_seconds > 0:
            report(f"[RESPAWN] жду reborn_banner {wait_seconds} сек")
            elapsed_focused = 0.0  # накапливаем ТОЛЬКО при фокусе
            last_ts = time.time()
            last_tick = -1

            while elapsed_focused < wait_seconds:
                now = time.time()
                dt = now - last_ts
                last_ts = now

                # если ожили сами — считаем revive
                st = ps_adapter.last() or {}
                if st.get("alive"):
                    _set_last_respawn(state, "revive")
                    report("[RESPAWN] ожили в ожидании — считаю type=revive")
                    _reset_macros_after_respawn(state)
                    return True, True

                # НЕТ фокуса: время НЕ идёт, только HUD и ждём
                if is_focused_now() is False:
                    tick = int(elapsed_focused)
                    if tick != last_tick:
                        last_tick = tick
                        report(f"[RESPAWN] unfocused, waiting for revive {tick}/{wait_seconds} сек.")
                    time.sleep(0.2)
                    continue

                # ЕСТЬ фокус: тикаем «фокус-время» и сканим только реборн
                elapsed_focused = min(wait_seconds, elapsed_focused + dt)

                tick = int(elapsed_focused)
                if tick != last_tick:
                    last_tick = tick
                    report(f"[RESPAWN] ожидание reborn… {tick}/{wait_seconds}")

                found = engine.scan_banner_key(
                    win, lang,
                    allowed_keys=["reborn_banner", "accept_button"]
                )
                if found and found[1] in ("reborn_banner", "accept_button"):
                    report("[RESPAWN] найден reborn — поднимаюсь (accept)")
                    ok = bool(engine.run_stand_up_once(
                        win, lang, timeout_ms=14_000,
                        allowed_keys=["reborn_banner", "accept_button"]
                    ))
                    if ok:
                        _set_last_respawn(state, "revive")
                        report("[RESPAWN] итог: type=revive")
                        _reset_macros_after_respawn(state)
                        return True, True
                    else:
                        report("[RESPAWN] reborn не сработал — повтор шага")
                        return False, False

                time.sleep(0.2)

            # таймаут ожидания → сначала пробуем точечно reborn
            report("[RESPAWN] таймер ожидания вышел")
            prefer_reborn = engine.scan_banner_key(
                win, lang,
                allowed_keys=["reborn_banner", "accept_button"]
            )
            if prefer_reborn and prefer_reborn[1] in ("reborn_banner", "accept_button"):
                report("[RESPAWN] по таймауту: reborn виден — поднимаюсь (accept)")
                ok = bool(engine.run_stand_up_once(
                    win, lang, timeout_ms=14_000,
                    allowed_keys=["reborn_banner", "accept_button"]
                ))
                rtype = "revive"
            else:
                report("[RESPAWN] по таймауту: reborn нет — поднимаюсь сам (death)")
                ok = bool(engine.run_stand_up_once(
                    win, lang, timeout_ms=14_000,
                    allowed_keys=["death_banner"]
                ))
                rtype = "self"

            if ok:
                _set_last_respawn(state, rtype)
                report(f"[RESPAWN] итог: type={rtype}")
                _reset_macros_after_respawn(state)
                return True, True
            return False, True

        # --- Без ожидания: пробуем reborn, иначе death ---
        found = engine.scan_banner_key(
            win, lang,
            allowed_keys=["reborn_banner", "accept_button", "death_banner"]
        )
        if found and found[1] in ("reborn_banner", "accept_button"):
            report("[RESPAWN] auto: найден reborn — поднимаюсь (accept)")
            ok = bool(engine.run_stand_up_once(
                win, lang, timeout_ms=14_000,
                allowed_keys=["reborn_banner", "accept_button"]
            ))
            rtype = "revive"
        elif found and found[1] == "death_banner":
            report("[RESPAWN] auto: найден death — поднимаюсь сам")
            ok = bool(engine.run_stand_up_once(
                win, lang, timeout_ms=14_000,
                allowed_keys=["death_banner"]
            ))
            rtype = "self"
        else:
            report("[RESPAWN] auto: баннеры не видны — общий подъём")
            ok = bool(engine.run_stand_up_once(
                win, lang, timeout_ms=14_000,
                allowed_keys=["reborn_banner", "accept_button", "death_banner"]
            ))
            rtype = "self"

        if ok:
            _set_last_respawn(state, rtype)
            report(f"[RESPAWN] итог: type={rtype}")
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
