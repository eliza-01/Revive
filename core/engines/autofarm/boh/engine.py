from __future__ import annotations
import time
import importlib
import os, re
from typing import Dict, Any, List, Tuple, Optional

import cv2
import numpy as np

from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.utils.colors import mask_for_colors_bgr, biggest_horizontal_band
from core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

# локальный счётчик перезапусков именно АФ-цикла (НЕ общий рестарт менеджера)
_RESTART_STREAK = 0
_RESTART_STREAK_LIMIT = 10

# В глобальной области добавляем список исключенных целей
excluded_targets = set()

# --- helpers ---
def _slugify_name_py(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[’`]", "'", s)
    s = re.sub(r"[^a-z0-9а-яё_' -]", "", s, flags=re.IGNORECASE)
    s = re.sub(r"[\s\-']+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s

def _abort(ctx_base) -> bool:
    f = ctx_base.get("should_abort")
    return bool(f and f())

def _capture_window_region(win: Dict, l: int, t: int, r: int, b: int):
    """
    Захват изображения с экрана в указанной области.
    """
    # Вместо чтения из файла, используем захват с экрана
    screen = capture_window_region_bgr(win, (l, t, r, b))
    if screen is None or screen.size == 0:
        print("[AF boh] Ошибка захвата экрана, пустой или некорректный кадр.")
        return None
    return screen


def _target_zone_ltrb(win: Dict) -> Tuple[int, int, int, int]:
    """Зона 500x120, верх-центр клиентской области."""
    w, h = int(win["width"]), int(win["height"])
    zw, zh = 500, 120
    l = max(0, (w - zw) // 2)
    t = max(0, 1)
    return (l, t, l + zw, t + zh)

def _target_sys_message_zone_ltrb(win: Dict) -> Tuple[int, int, int, int]:
    """Зона для поиска sys_message: отступ слева 24px, отступ снизу 240px, размер зоны 100x17."""
    w, h = int(win["width"]), int(win["height"])
    zw, zh = 93, 40
    l = 22
    t = max(0, h - 220 - zh)
    return (l, t, l + zw, t + zh)

def _hp_palettes(server: str) -> Tuple[List[Tuple[int,int,int]], List[Tuple[int,int,int]], int]:
    """
    Из core.servers.<server>.zones.state берём:
      - COLORS['hp_alive_monster_rgb_boh']
      - COLORS['hp_dead_monster_rgb_boh']
      - HP_COLOR_TOLERANCE
    """
    try:
        m = importlib.import_module(f"core.servers.{server}.zones.state")
        cd = getattr(m, "COLORS", {}) or {}
        alive = list(cd.get("hp_alive_monster_rgb_boh", []))
        dead  = list(cd.get("hp_dead_monster_rgb_boh",  []))
        tol   = int(getattr(m, "HP_COLOR_TOLERANCE", 2))
        if alive or dead:
            return alive, dead, tol
    except Exception:
        pass
    # fallback
    return ([(139, 98, 96), (128, 70, 68), (111, 23, 19), (136, 28, 24), (171, 48, 34)],
            [(70, 61, 62), (61, 49, 50), (48, 28, 27), (57, 32, 31), (67, 38, 36)],
            2)

_debug_dump_done = False

def _detect_target_bands(win: Dict, server: str):
    """Возвращает (rect_alive, rect_any) в локальных коорд. зоны."""
    global _debug_dump_done
    l, t, r, b = _target_zone_ltrb(win)
    img = capture_window_region_bgr(win, (l, t, r, b))
    if img is None or img.size == 0:
        print("[AF boh][hp] frame: empty → UNKNOWN")
        return None, None

    alive_rgb, dead_rgb, tol = _hp_palettes(server)
    mask_alive = mask_for_colors_bgr(img, colors_rgb=alive_rgb, tol=tol)

    if dead_rgb:
        mask_dead  = mask_for_colors_bgr(img, colors_rgb=dead_rgb,  tol=tol)
        mask_any = np.bitwise_or(mask_alive, mask_dead)
    else:
        mask_any = mask_alive.copy()

    rect_alive = biggest_horizontal_band(mask_alive)
    rect_any   = biggest_horizontal_band(mask_any)

    if not _debug_dump_done:
        try:
            dbg_dir = os.path.abspath("debug_af_boh")
            os.makedirs(dbg_dir, exist_ok=True)
            cv2.imwrite(os.path.join(dbg_dir, "target_zone_bgr.png"), img)
            cv2.imwrite(os.path.join(dbg_dir, "mask_alive.png"), mask_alive)
            cv2.imwrite(os.path.join(dbg_dir, "mask_any.png"), mask_any)
            print(f"[AF boh][debug] saved target_zone_bgr.png / mask_alive.png / mask_any.png to {dbg_dir}")
        except Exception as e:
            print(f"[AF boh][debug] save failed: {e}")
        _debug_dump_done = True

    return rect_alive, rect_any

def _has_target_by_hp(win: Dict, server: str, tries: int = 3, delay_ms: int = 200, should_abort=None) -> bool:
    """Есть ли вообще цель (любой «полосатый» цвет: alive+dead)? С досрочной отменой."""
    for i in range(max(1, tries)):
        if should_abort and should_abort():
            return False
        _, rect_any = _detect_target_bands(win, server)
        if rect_any:
            x, y, w, h = rect_any
            ok = (w >= 40 and h >= 3)
            print(f"[AF boh][target] any-colors → {'YES' if ok else 'NO'} (w={w},h={h}) try={i+1}/{tries}")
            if ok:
                return True
        time.sleep(delay_ms / 1000.0)
    return False

def _has_target_by_hp(win: Dict, server: str, tries: int = 3, delay_ms: int = 200, should_abort=None) -> bool:
    """Есть ли вообще цель (любой «полосатый» цвет: alive+dead)? С досрочной отменой."""
    for i in range(max(1, tries)):
        if should_abort and should_abort():
            return False
        _, rect_any = _detect_target_bands(win, server)
        if rect_any:
            x,y,w,h = rect_any
            ok = (w >= 40 and h >= 3)
            print(f"[AF boh][target] any-colors → {'YES' if ok else 'NO'} (w={w},h={h}) try={i+1}/{tries}")
            if ok:
                return True
        time.sleep(delay_ms/1000.0)
    return False

def _target_alive_by_hp(win: Dict, server: str) -> Optional[bool]:
    """True  — «живая» полоса присутствует, False — полосы нет или только «мертвые» оттенки, None  — кадр пустой/ошибка."""
    rect_alive, rect_any = _detect_target_bands(win, server)
    if rect_any is None:
        return None
    if not rect_any:
        return False
    if rect_alive:
        _, _, w, h = rect_alive
        alive = (w >= 40 and h >= 3)
        print(f"[AF boh][hp/alive] → {'ALIVE' if alive else 'DEAD'}")
        return alive
    print("[AF boh][hp/alive] → DEAD (only dead colors)")
    return False

def _zone_monster_display_names(server: str, zone_id: str, lang: str) -> List[str]:
    try:
        from core.engines.autofarm.zone_repo import get_zone_info
        info = get_zone_info(server, zone_id, lang or "eng")
        names = []
        for m in (info.get("monsters") or []):
            if isinstance(m, dict):
                names.append(m.get("name") or m.get("slug") or "")
            elif isinstance(m, str):
                names.append(m)
        return [n for n in names if n]
    except Exception:
        return []

def _send_chat(ex: FlowOpExecutor, text: str, wait_ms: int = 500) -> bool:
    flow = [
        {"op": "send_message", "layout": "en", "text": text, "wait_ms": 60},
        {"op": "sleep", "ms": max(0, int(wait_ms))}
    ]
    return bool(run_flow(flow, ex))

def _send_target_with_ru_name(ex: FlowOpExecutor, mob_name: str, wait_ms: int = 500) -> bool:
    flow = [
        {"op": "press_enter"},
        {"op": "enter_text", "layout": "en", "text": "/target "},
        {"op": "set_layout", "layout": "ru", "delay_ms": 120},
        {"op": "enter_text", "layout": "ru", "text": mob_name, "wait_ms": 60},
        {"op": "press_enter"},
        {"op": "set_layout", "layout": "en", "delay_ms": 120},
        {"op": "sleep", "ms": max(0, int(wait_ms))}
    ]
    return bool(run_flow(flow, ex))

def _press_key(ex: FlowOpExecutor, key_digit: str) -> bool:
    key_digit = str(key_digit)[:2]
    flow = [{"op": "send_arduino", "cmd": key_digit, "delay_ms": 0}]
    return bool(run_flow(flow, ex))

def _press_esc(ex: FlowOpExecutor) -> bool:
    return bool(run_flow([{"op": "send_arduino", "cmd": "esc", "delay_ms": 0}], ex))

# --- основной сценарий ---
def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    global _RESTART_STREAK

    server = (ctx_base["server"] or "boh").lower()
    lang = (ctx_base["get_language"]() or "eng").lower()
    win = ctx_base["get_window"]()
    print(f"[AF boh] Window size: {win['width']}x{win['height']}")

    if not win:
        ctx_base["on_status"]("[AF boh] окно не найдено", False)
        return False
    print(f"[AF boh] cycle start; win={win['width']}x{win['height']}")

    zones = {
        "fullscreen": {"fullscreen": True},
        "target_zone": {
            "left": _target_zone_ltrb(win)[0],
            "top": _target_zone_ltrb(win)[1],
            "width": 400,
            "height": 80,
        }
    }
    ctx = FlowCtx(
        server=server,
        controller=ctx_base["controller"],
        get_window=lambda: win,
        get_language=lambda: lang,
        zones=zones,
        templates={},
        extras={},
    )
    ex = FlowOpExecutor(ctx, on_status=ctx_base["on_status"])

    last_target_alive = None  # Переменная для хранения состояния цели

    while True:
        if _abort(ctx_base):
            ctx_base["on_status"]("[AF boh] остановлено пользователем", None)
            return False

        # 1) /targetnext
        _send_chat(ex, "/targetnext", wait_ms=1000)
        if _abort(ctx_base):
            return False

        # NEW: есть ли вообще цель (полоса любого цвета)
        has_any = _has_target_by_hp(win, server, tries=1, delay_ms=150, should_abort=lambda: _abort(ctx_base))
        current_alive = _target_alive_by_hp(win, server)

        if current_alive is None:
            has_any = _has_target_by_hp(win, server, tries=1, delay_ms=150, should_abort=lambda: _abort(ctx_base))
            if has_any and not current_alive:
                # возможная задержка обновления HP-полосы — короткая перепроверка
                time.sleep(0.2)
                current_alive = _target_alive_by_hp(win, server)

            print(f"[AF boh] /targetnext → has_any={has_any} alive={current_alive}")
            # захват дал пустой кадр → не выходим, а делаем несколько повторов
            for i in range(10):
                time.sleep(0.3)
                # обновим info окна на случай его смещения/ресайза
                try:
                    win = ctx_base["get_window"]() or win
                except Exception:
                    pass
                current_alive = _target_alive_by_hp(win, server)
                if current_alive is not None:
                    print(f"[AF boh][retry] кадр ок на попытке {i + 1}/10")
                    break
            if current_alive is None:
                # пропускаем тик, главный цикл продолжается
                print("[AF boh][warn] кадр пустой → пропускаю тик")
                current_alive = False  # форсим переход в ветку перебора имён

        print(f"[AF boh] /targetnext → has_any={has_any} alive={current_alive}")

        if has_any and current_alive:
            ctx_base["on_status"]("[AF boh] цель получена /targetnext", True)
            if _abort(ctx_base):
                return False
            # цель взяли не по имени
            ctx_base["af_current_target_name"] = None
            ok = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
            if _abort(ctx_base):
                return False
            if ok:
                _RESTART_STREAK = 0
                print("[AF boh] цель добита → новый поиск", flush=True)
                # очистить исключённые цели после убийства
                excluded_targets.clear()
                continue
            else:
                # если в бою словили "цель не видна" — переходим к перебору имён
                if ctx_base.get("af_unvisible"):
                    print("[AF boh] 'цель не видна' после /targetnext → начинаем перебор имён")
                    ctx_base["af_unvisible"] = False
                    zone_id = (cfg or {}).get("zone") or ""
                    names = _zone_monster_display_names(server, zone_id, lang)

                    allowed_slugs = set((cfg or {}).get("monsters") or [])
                    if allowed_slugs:
                        names = [n for n in names if _slugify_name_py(n) in allowed_slugs]
                        print(f"[AF boh] фильтр по чекбоксам: {len(names)} имён")
                        if not names:
                            ctx_base["on_status"]("[AF boh] все мобы сняты галками — пропускаю тик", None)
                            time.sleep(0.5)
                            continue

                    if names and all(nm in excluded_targets for nm in names):
                        print("[AF boh] все цели в blacklist → очищаю список")
                        excluded_targets.clear()

                    if not names:
                        ctx_base["on_status"]("[AF boh] нет списка монстров зоны", False)
                        return False

                    found = False
                    for nm in names:
                        if nm in excluded_targets:
                            print(f"[AF boh] skip (blacklisted): {nm}")
                            continue
                        if _abort(ctx_base):
                            return False
                        _send_target_with_ru_name(ex, nm, wait_ms=500)
                        if _abort(ctx_base):
                            return False
                        if _has_target_by_hp(win, server, tries=3, delay_ms=250, should_abort=lambda: _abort(ctx_base)):
                            ctx_base["on_status"](f"[AF boh] цель найдена (fallback): {nm}", True)
                            ctx_base["af_current_target_name"] = nm
                            ok2 = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
                            if _abort(ctx_base):
                                return False

                            # если снова "цель не видна" — чёрный список и дальше
                            if ctx_base.get("af_unvisible"):
                                excluded_targets.add(nm)
                                ctx_base["af_unvisible"] = False
                                print(f"[AF boh] '{nm}' невидима → в чёрный список; ищем дальше")
                                continue

                            if ok2:
                                _RESTART_STREAK = 0
                                excluded_targets.clear()
                                found = True
                                break

                    if found:
                        continue
                    _RESTART_STREAK += 1
                    ctx_base["on_status"](f"[AF boh] цель не найдена (fallback), рестарт цикла #{_RESTART_STREAK}", None)
                else:
                    _RESTART_STREAK += 1
        else:
            # /targetnext не дал живую цель → перебираем имена
            zone_id = (cfg or {}).get("zone") or ""
            names = _zone_monster_display_names(server, zone_id, lang)

            allowed_slugs = set((cfg or {}).get("monsters") or [])
            if allowed_slugs:
                names = [n for n in names if _slugify_name_py(n) in allowed_slugs]
                print(f"[AF boh] фильтр по чекбоксам: {len(names)} имён")
                if not names:
                    ctx_base["on_status"]("[AF boh] все мобы сняты галками — пропускаю тик", None)
                    time.sleep(0.5)
                    continue

            if names and all(nm in excluded_targets for nm in names):
                print("[AF boh] все цели в blacklist → очищаю список")
                excluded_targets.clear()

            if not names:
                ctx_base["on_status"]("[AF boh] нет списка монстров зоны", False)
                return False

            found = False
            for nm in names:
                if nm in excluded_targets:
                    print(f"[AF boh] Пропускаем цель (blacklisted): {nm}")
                    continue

                if _abort(ctx_base):
                    return False
                _send_target_with_ru_name(ex, nm, wait_ms=500)
                if _abort(ctx_base):
                    return False
                if _has_target_by_hp(win, server, tries=3, delay_ms=250, should_abort=lambda: _abort(ctx_base)):
                    # NEW: если цель мёртвая (труп) → в чёрный список и к следующему имени
                    alive_state = _target_alive_by_hp(win, server)
                    if alive_state is False:
                        excluded_targets.add(nm)
                        print(f"[AF boh] '{nm}' мёртв → blacklist до следующего убийства")
                        continue

                    found = True
                    ctx_base["on_status"](f"[AF boh] цель найдена: {nm}", True)
                    ctx_base["af_current_target_name"] = nm
                    if _abort(ctx_base):
                        return False
                    ok = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
                    if _abort(ctx_base):
                        return False

                    # если в бою поймали "цель не видна" — заносим имя в чёрный список и пробуем следующего
                    if ctx_base.get("af_unvisible"):
                        excluded_targets.add(nm)
                        ctx_base["af_unvisible"] = False
                        print(f"[AF boh] '{nm}' невидима → в чёрный список; ищем дальше")
                        found = False
                        continue

                    if ok:
                        _RESTART_STREAK = 0
                        excluded_targets.clear()
                        found = False  # сразу уходим на новый круг поиска
                        break

            if found:
                continue  # на всякий

            _RESTART_STREAK += 1
            ctx_base["on_status"](f"[AF boh] цель не найдена, рестарт цикла #{_RESTART_STREAK}", None)

        if _RESTART_STREAK >= _RESTART_STREAK_LIMIT:
            try:
                _send_chat(ex, "/unstuck", wait_ms=2222)
                _press_esc(ex)
                print("[AF boh] streak лимит → отправлен /unstuck")
            except Exception as e:
                print(f"[AF boh] /unstuck failed: {e}")
            ctx_base["on_status"]("[AF boh] 10 безрезультатных циклов → запустить ПОЛНЫЙ ЦИКЛ (как после смерти)", False)
            return False

        time.sleep(0.3)



def _attack_cycle(ex: FlowOpExecutor, ctx_base: Dict[str, Any], server: str, lang: str,
                  win: Dict, cfg: Dict[str, Any]) -> bool:
    """
    Движок атаки: пока цель жива — крутим круги скиллов.
    """
    skills = list((cfg or {}).get("skills") or [])
    if not skills:
        ctx_base["on_status"]("[AF boh] нет настроенных скиллов", False)
        return False

    plan: List[Dict[str, Any]] = []
    for s in skills:
        k = str(s.get("key") or "1")
        cd = max(1, int(s.get("cast_ms") or 2000)) / 1000.0
        plan.append({"key": k, "cd": cd, "last": 0.0, "used": False})

    probe_sleep = max((it["cd"] for it in plan), default=0.5)

    start_ts = time.time()
    hard_timeout = 45.0

    def ready(item) -> bool:
        return (time.time() - (item["last"] or 0.0)) >= item["cd"]

    while True:
        if _abort(ctx_base):
            ctx_base["on_status"]("[AF boh] остановлено пользователем", None)
            return False

        if (time.time() - start_ts) > hard_timeout:
            ctx_base["on_status"]("[AF boh] таймаут атаки", False)
            print("[AF boh] таймаут атаки")
            return False

        alive = _target_alive_by_hp(win, server)
        if alive is False:
            ctx_base["on_status"]("[AF boh] цель мертва/пропала", True)
            time.sleep(0.2)
            return True
        if alive is None:
            time.sleep(probe_sleep)
            continue

        candidate = next((it for it in plan if (not it["used"]) and ready(it)), None)
        if not candidate:
            ready_any = [it for it in plan if ready(it)]
            candidate = ready_any[0] if ready_any else None

        if candidate:
            if _press_key(ex, candidate["key"]):
                if _abort(ctx_base):
                    return False
                candidate["last"] = time.time()
                candidate["used"] = True
            time.sleep(probe_sleep)
        else:
            time.sleep(probe_sleep)

        # Завершение круга скиллов
        if all(it["used"] for it in plan):
            print("[AF boh] круг скиллов завершён → новый круг", flush=True)

            # Проверка на видимость новой цели
            zone_id = (cfg or {}).get("zone") or ""
            if _check_target_visibility(ex, server, lang, win, zone_id):
                _send_chat(ex, "/", wait_ms=22)
                _send_chat(ex, "/", wait_ms=22)
                _press_esc(ex)
                # сигнал наружу: цель невидима → нужно сменить цель
                ctx_base["af_unvisible"] = True
                print("[AF boh] цель не видна → выходим из attack_cycle для смены цели")
                return False


# Функция для проверки видимости цели после первой атаки
def _check_target_visibility(ex: FlowOpExecutor, server: str, lang: str, win: Dict, zone_id: str) -> bool:
    """
    Проверяем видимость цели после первой атаки.
    Теперь используем OpenCV для поиска изображения, а не match_in_zone.
    """
    image_path = f"core/engines/autofarm/{server}/templates/{lang}/sys_messages/target_unvisible.png"

    # Загружаем изображение для поиска
    target_img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if target_img is None:
        print(f"[AF boh] Ошибка загрузки изображения {image_path}")
        return False  # Если изображение не найдено, цель видна

    # Получаем зону для поиска sys_message
    l, t, r, b = _target_sys_message_zone_ltrb(win)

    # Используем новую функцию для захвата экрана
    search_zone = _capture_window_region(win, l, t, r, b)

    if search_zone is None or search_zone.size == 0:
        print(f"[AF boh] Ошибка захвата экрана в зоне {l},{t},{r},{b}")
        return False  # Если не удалось захватить экран, цель видна

    # Проверка на корректную размерность массива (оно должно быть 2D или 3D)
    if search_zone.ndim != 3:
        print(f"[AF boh] Ошибка: захваченный экран имеет неправильную размерность (ndim={search_zone.ndim})")
        return False  # Если размерность неправильная, цель видна

    # Сохраняем захваченную область для дебага
    try:
        dbg_dir = os.path.abspath("debug_af_boh")
        os.makedirs(dbg_dir, exist_ok=True)
        debug_image_path = os.path.join(dbg_dir, "captured_zone.png")
        cv2.imwrite(debug_image_path, search_zone)
        print(f"[AF boh][debug] saved captured zone to {debug_image_path}")
    except Exception as e:
        print(f"[AF boh][debug] failed to save captured zone: {e}")

    # Преобразуем в оттенки серого для удобства поиска
    search_zone_gray = cv2.cvtColor(search_zone, cv2.COLOR_BGR2GRAY)

    # Используем метод сравнения шаблонов OpenCV (например, `cv2.matchTemplate`)
    result = cv2.matchTemplate(search_zone_gray, target_img, cv2.TM_CCOEFF_NORMED)

    # Пороговое значение для нахождения шаблона
    threshold = 0.40
    if np.any(result >= threshold):
        print(f"[AF boh] Цель не видна, отсылаем /s команду.")
        return True  # Если шаблон найден, цель не видна

    # Если совпадение не найдено, цель видна
    print(f"[AF boh] Цель видна — продолжаем бой.")
    return False