# core/engines/respawn/server/boh/rules.py
from typing import Any, Dict, Optional, Tuple, List, Callable
import time
import os
import tempfile

import cv2
import numpy as np

from core.state.pool import pool_get, pool_write
from core.orchestrators.snapshot import Snapshot
from core.logging import console

# ↓ эти нужны утилите _perform_stand_up_phase
from core.vision.zones import compute_zone_ltrb
from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.matching.template_matcher_2 import match_multi_in_zone
from .respawn_data import ZONES, TEMPLATES
from .templates.resolver import resolve as tpl_resolve

RESPAWN_TIMEOUT = 8_000


def run_step(
    *,
    state: Dict[str, Any],
    ps_adapter,
    controller,
    snap: Snapshot,
    helpers: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, bool]:
    """
    Правило шага Respawn для текущего сервера. Контракт: (ok, advance).

    Сценарий:
      - если feature на паузе — не тикаем (ожидание)
      - при ожидании можем искать ТОЛЬКО reborn_banner/accept_button
      - по таймауту: если виден reborn → revive, иначе → self (death)
      - фиксируем features.respawn.last_respawn.type и бампим макросы
    """
    helpers = helpers or {}

    def _paused_now() -> Tuple[bool, str]:
        try:
            p = bool(pool_get(state, "features.respawn.paused", False))
            reason = str(pool_get(state, "features.respawn.pause_reason", "") or "")
            return p, reason
        except Exception:
            return False, ""

    # окно и пауза
    if not snap.has_window:
        return False, False

    paused, reason = _paused_now()
    if paused:
        txt = f"[RESPAWN] пауза: {reason or 'остановлено'} — жду"
        console.hud("ok", txt)
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

            elapsed_active = 0.0  # считаем только «когда не на паузе»
            last_ts = time.time()

            # для «тикания» и обратного отсчёта
            last_tick = -1          # сколько прошло (целых секунд)
            last_remaining = None   # сколько осталось (для HUD)

            last_reason = ""
            while elapsed_active < wait_seconds:
                now = time.time()
                dt = now - last_ts
                last_ts = now

                paused, reason = _paused_now()
                if paused:
                    if reason != last_reason:
                        last_reason = reason
                        console.log(f"[RESPAWN] paused ({reason})… {int(elapsed_active)}/{wait_seconds}s")
                    time.sleep(0.2)
                    continue

                # активны — тикаем и сканим только reborn
                elapsed_active = min(wait_seconds, elapsed_active + dt)
                tick = int(elapsed_active)

                # обновляем обратный отсчёт в HUD ровно раз в секунду
                remaining = max(0, wait_seconds - tick)
                if remaining != last_remaining:
                    last_remaining = remaining
                    console.hud("ok", f"[RESPAWN] ожидание reborn: {remaining}s")

                if tick != last_tick:
                    last_tick = tick
                    console.log(f"[RESPAWN] ожидание reborn… {tick}/{wait_seconds}s")

                found = engine.scan_banner_key(
                    win, lang,
                    allowed_keys=["reborn_banner", "accept_button"]
                )

                # ожили сами — считаем revive
                st = ps_adapter.last() or {}
                if st.get("alive"):
                    _set_last_respawn(state, "revive")
                    console.hud("succ", "[RESPAWN] ожили во время ожидания (revive)")
                    _reset_macros_after_respawn(state)
                    return True, True

                time.sleep(0.2)

                if found and found[1] in ("reborn_banner", "accept_button"):
                    console.hud("ok", "[RESPAWN] найден reborn — поднимаюсь (accept)")
                    ok = bool(_perform_stand_up_phase(
                        engine=engine,
                        window=win,
                        lang=lang,
                        timeout_ms=RESPAWN_TIMEOUT,
                        allowed_keys=["reborn_banner", "accept_button"],
                        is_alive_cb=lambda: bool(ps_adapter.last().get("alive")),
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
                ok = bool(_perform_stand_up_phase(
                    engine=engine,
                    window=win,
                    lang=lang,
                    timeout_ms=RESPAWN_TIMEOUT,
                    allowed_keys=["reborn_banner", "accept_button"],
                    is_alive_cb=lambda: bool(ps_adapter.last().get("alive")),
                ))
                rtype = "revive"
            else:
                console.hud("ok", "[RESPAWN] по таймауту: reborn нет — поднимаюсь сам (death)")
                ok = bool(_perform_stand_up_phase(
                    engine=engine,
                    window=win,
                    lang=lang,
                    timeout_ms=RESPAWN_TIMEOUT,
                    allowed_keys=["death_banner"],
                    is_alive_cb=lambda: bool(ps_adapter.last().get("alive")),
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
            ok = bool(_perform_stand_up_phase(
                engine=engine,
                window=win,
                lang=lang,
                timeout_ms=RESPAWN_TIMEOUT,
                allowed_keys=["reborn_banner", "accept_button"],
                is_alive_cb=lambda: bool(ps_adapter.last().get("alive")),
            ))
            rtype = "revive"
        elif found and found[1] == "death_banner":
            console.hud("ok", "[RESPAWN] auto: найден death — поднимаюсь сам")
            ok = bool(_perform_stand_up_phase(
                engine=engine,
                window=win,
                lang=lang,
                timeout_ms=RESPAWN_TIMEOUT,
                allowed_keys=["death_banner"],
                is_alive_cb=lambda: bool(ps_adapter.last().get("alive")),
            ))
            rtype = "self"
        else:
            console.hud("ok", "[RESPAWN] auto: баннеры не видны — общий подъём")
            ok = bool(_perform_stand_up_phase(
                engine=engine,
                window=win,
                lang=lang,
                timeout_ms=RESPAWN_TIMEOUT,
                allowed_keys=["reborn_banner", "accept_button", "death_banner"],
                is_alive_cb=lambda: bool(ps_adapter.last().get("alive")),
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


# ---- debug helper (ROI + шаблоны) ---------------------------------------
def _debug_open_respawn_probe(
    window: Dict[str, Any],
    lang: str,
    allowed_keys: List[str],
    ltrb: Tuple[int, int, int, int],
    filename_hint: str = "probe"
) -> None:
    try:
        roi = capture_window_region_bgr(window, ltrb)
        if roi is None or roi.size == 0:
            console.log("[respawn/dbg] zone capture is empty")
            return

        tiles = []
        lang = (lang or "rus").lower()
        for key in (allowed_keys or []):
            parts = TEMPLATES.get(key)
            if not parts:
                continue
            p = tpl_resolve(lang, *parts)
            if not p:
                console.log(f"[respawn/dbg] template not resolved for key={key}")
                continue
            img = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            if img is None or img.size == 0:
                console.log(f"[respawn/dbg] template read failed for key={key}: {p}")
                continue

            if img.ndim == 2:
                icon = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.ndim == 3 and img.shape[2] == 4:
                icon = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            else:
                icon = img

            icon = cv2.resize(icon, (70, 70), interpolation=cv2.INTER_AREA)
            icon = cv2.copyMakeBorder(icon, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=(0, 255, 0))
            label_h = 18
            tile = np.zeros((icon.shape[0] + label_h, icon.shape[1], 3), dtype=np.uint8)
            tile[:icon.shape[0], :icon.shape[1]] = icon
            cv2.putText(tile, key[:16], (2, tile.shape[0]-4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
            tiles.append(tile)

        strip = None
        if tiles:
            strip = np.hstack(tiles)
            header = np.zeros((22, strip.shape[1], 3), dtype=np.uint8)
            cv2.putText(header, "SEARCH TEMPLATES:", (6, 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 1, cv2.LINE_AA)
            strip = np.vstack([header, strip])

        roi_bgr = roi if roi.ndim == 3 else cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
        if strip is not None:
            W = max(roi_bgr.shape[1], strip.shape[1])

            def _pad_w(img):
                if img.shape[1] == W:
                    return img
                pad = np.zeros((img.shape[0], W - img.shape[1], 3), dtype=np.uint8)
                return np.hstack([img, pad])

            out = np.vstack([_pad_w(roi_bgr), _pad_w(strip)])
        else:
            out = roi_bgr

        ts = int(time.time())
        path = os.path.join(tempfile.gettempdir(), f"revive_dbg_respawn_{filename_hint}_{ts}.png")
        cv2.imwrite(path, out)
        console.log(f"[respawn/dbg] saved -> {path}")
        try:
            os.startfile(path)  # Windows
        except Exception:
            try:
                import subprocess, platform
                if platform.system() == "Darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
            except Exception:
                pass
    except Exception as e:
        console.log(f"[respawn/dbg] snapshot error: {e}")


# ---- stand-up phase ------------------------------------------------------
def _perform_stand_up_phase(
    *,
    engine,
    window: Dict,
    lang: str,
    timeout_ms: int,
    allowed_keys: List[str],
    is_alive_cb: Callable[[], bool],
) -> bool:
    """
    Оркестрация одной активной фазы подъёма:
      - цикл поиска разрешённых ключей
      - клик по выбранной точке
      - короткое подтверждение (alive/исчезновение баннера)
    """
    console.hud("ok", "[respawn] Жду кнопку в город или рес")

    zone_decl = ZONES.get("death_banners") or ZONES.get("fullscreen")
    if not zone_decl or not window:
        return False
    ltrb = compute_zone_ltrb(window, zone_decl)

    debug_on = False
    try:
        debug_on = bool(getattr(engine, "_debug_enabled")() is True)
    except Exception:
        pass

    if debug_on:
        console.log(f"[respawn] scan zone={ltrb} thr={engine.click_threshold:.2f} keys={allowed_keys}")
        try:
            _debug_open_respawn_probe(window, lang, allowed_keys, ltrb, filename_hint="standup")
        except Exception:
            pass

    deadline = time.time() + max(1, int(timeout_ms)) / 1000.0
    last_seen_key: Optional[str] = None
    last_click_ts = 0.0

    while time.time() < deadline:
        if is_alive_cb():
            console.hud("succ", "[respawn] Возродились")
            return True

        # точечный последовательный поиск через движок
        res = engine.scan_banner_key(
            window=window,
            lang=(lang or "rus").lower(),
            allowed_keys=allowed_keys,
        )

        if res is None:
            if last_seen_key == "death_banner":
                console.hud("ok", "[respawn] кнопка пропала. Ждём подъём")
            elif last_seen_key == "reborn_banner":
                console.hud("ok", "[respawn] окно реса пропало. Ждём подъём")
            load_deadline = time.time() + 0.4
            while time.time() < load_deadline:
                if is_alive_cb():
                    console.hud("succ", "[respawn] Возродились")
                    return True
                time.sleep(0.05)
            time.sleep(0.05)
            continue

        (pt, key) = res
        last_seen_key = key

        now = time.time()
        if now - last_click_ts < 0.6:
            time.sleep(0.05)
            continue

        click_x, click_y = engine.pick_click_point_for_key(window, lang, key, pt)
        confirm_wait_s = engine.confirm_timeout_s
        if key == "reborn_banner" or key == "accept_button":
            console.hud("ok", "[respawn] соглашаемся на рес")
            confirm_wait_s = 5.0
        elif key == "death_banner":
            console.hud("ok", "[respawn] встаём в город")

        engine.click_at(click_x, click_y)
        last_click_ts = now

        confirm_deadline = now + float(confirm_wait_s)
        while time.time() < confirm_deadline:
            if is_alive_cb():
                console.hud("succ", "[respawn] Возродились")
                return True
            res2 = match_multi_in_zone(
                window=window,
                zone_ltrb=ltrb,
                server=engine.server,
                lang=(lang or "rus").lower(),
                templates_map=TEMPLATES,
                key_order=allowed_keys,
                threshold=engine.click_threshold,
                engine="respawn",
                scales=(1.0, 0.95, 1.05),
                debug=debug_on,
            )
            if res2 is None:
                if key == "death_banner":
                    console.hud("ok", "[respawn] кнопка пропала. Ждём подъём")
                elif key in ("reborn_banner", "accept_button"):
                    console.hud("ok", "[respawn] окно реса пропало. Ждём подъём")
                break
            time.sleep(0.05)

        time.sleep(0.05)

    console.hud("err", "[respawn] не удалось подняться")
    return False


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
