from __future__ import annotations
import time, importlib
from typing import Dict, Any, List, Tuple, Optional

from core.vision.capture.window_bgr_capture import capture_window_region_bgr
from core.vision.matching.template_matcher import match_in_zone
from core.vision.utils.colors import mask_for_colors_bgr, biggest_horizontal_band
from core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

# локальный счетчик перезапусков именно АФ-цикла (НЕ общий рестарт менеджера)
_RESTART_STREAK = 0
_RESTART_STREAK_LIMIT = 10

# --- helpers ---

def _window() -> Dict:  # заглушка-тип для mypy
    return {}

def _target_zone_ltrb(win: Dict) -> Tuple[int, int, int, int]:
    """
    Зона 400x80, верх-центр клиентской области.
    Возвращаем (L, T, R, B) в client-координатах.
    """
    w, h = int(win["width"]), int(win["height"])
    zw, zh = 400, 80
    l = max(0, (w - zw) // 2)
    t = max(0, 10)  # небольшой отступ от верхней кромки
    return (l, t, l + zw, t + zh)

def _has_target_selected(win: Dict, server: str, lang: str) -> bool:
    """
    Проверяем наличие индикатора выбранной цели по шаблону target_init.png в target-зоне.
    """
    zone = _target_zone_ltrb(win)
    pt = match_in_zone(win, zone, server, lang, ["interface", "target_init.png"], threshold=0.87)
    return bool(pt)

def _hp_colors_from_profile(server: str) -> List[Tuple[int,int,int]]:
    """
    "Те же цвета, что для нашего HP".
    Пытаемся вытащить из серверного профиля/модуля; при неудаче — разумный дефолт.
    (СПЕЦИАЛЬНО: не плодим новую конфигурацию)
    """
    # 1) попробуем core.servers.<server>.ui_colors.HP_COLORS_RGB
    try:
        m = importlib.import_module(f"core.servers.{server}.ui_colors")
        colors = getattr(m, "HP_COLORS_RGB", None)
        if colors: return list(colors)
    except Exception:
        pass
    # 2) fallback — «красные» оттенки полосы HP (RGB)
    return [(210, 30, 30), (230, 60, 60), (180, 20, 20)]

def _target_alive_by_hp(win: Dict, server: str) -> Optional[bool]:
    """
    Определяем «жив/мертв» по наличию горизонтальной полосы HP в target-зоне
    теми же цветами, что используем для собственного HP.
    Возврат:
      True  — есть полоса (жив)
      False — полосы нет/исчезла (мертв)
      None  — не удалось решить (нет кадра и т.п.)
    """
    zone = {
        "left": _target_zone_ltrb(win)[0],
        "top": _target_zone_ltrb(win)[1],
        "width": 400,
        "height": 80
    }
    img = capture_window_region_bgr(win, (zone["left"], zone["top"], zone["left"]+zone["width"], zone["top"]+zone["height"]))
    if img is None or img.size == 0:
        return None
    colors = _hp_colors_from_profile(server)  # RGB list
    mask = mask_for_colors_bgr(img, colors_rgb=colors, tol=3)
    rect = biggest_horizontal_band(mask)  # (x,y,w,h) самой широкой «полосы»
    if not rect:
        return False  # полосы нет — цель мертва/не выбрана
    _, _, w, h = rect
    # простое правило: если есть полоса заметной ширины и высоты — жив
    if w >= 40 and h >= 3:
        return True
    return False

def _zone_monster_display_names(server: str, zone_id: str, lang: str) -> List[str]:
    """
    Достаём display-имена монстров зоны из zone_repo (то, что видит игрок в клиенте).
    """
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
    """
    Пишем чат-команду через готовый FlowOp 'send_message' + маленькие «подметания».
    НИЧЕГО НОВОГО не изобретаем.
    """
    flow = [
        {"op": "send_arduino", "cmd": "backspace_click", "delay_ms": 12, "count": 30},  # зачистка строки
        {"op": "send_message", "layout": "en", "text": text, "wait_ms": 60},
        {"op": "sleep", "ms": max(0, int(wait_ms))}
    ]
    return bool(run_flow(flow, ex))

def _press_key(ex: FlowOpExecutor, key_digit: str) -> bool:
    """
    Отправляем на ардуино цифру 0-9 (как и в макросах).
    Через существующий op 'send_arduino'.
    """
    key_digit = str(key_digit)[:2]
    flow = [{"op": "send_arduino", "cmd": key_digit, "delay_ms": 0}]
    return bool(run_flow(flow, ex))

# --- основной сценарий ---

def start(ctx_base: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """
    Один «проход» АФ:
      1) /targetnext → проверка цели → если нет, перебор /target <имя> по списку зоны
      2) если цель есть → атакуем выбранными скиллами с приоритетом "ещё не использован в круге"
         и разрешением брать любой готовый (cooldown) при отсутствии «новых».
      3) если цель умирает → цикл завершён, обнуляем локальный streak.
      4) если цели не нашли вовсе → увеличиваем локальный streak, при 10 — просим «полный цикл».
    Возврат True/False — просто статус прохода (сервис дальше сам решит, когда снова запустить).
    """
    global _RESTART_STREAK

    server = (ctx_base["server"] or "boh").lower()
    lang   = (ctx_base["get_language"]() or "eng").lower()
    win    = ctx_base["get_window"]()
    if not win:
        ctx_base["on_status"]("[AF bo h] окно не найдено", False)
        return False

    # статические зоны для FlowCtx (fullscreen уже есть у executor'а)
    zones = {
        "fullscreen": {"fullscreen": True},
        "target_zone": {  # передадим абсолют как «left/top/width/height»
            "left":  _target_zone_ltrb(win)[0],
            "top":   _target_zone_ltrb(win)[1],
            "width": 400,
            "height":80,
        }
    }
    ctx = FlowCtx(
        server=server,
        controller=ctx_base["controller"],
        get_window=lambda: win,            # Фиксируем окно на время прохода
        get_language=lambda: lang,
        zones=zones,
        templates={},   # parts передаем напрямую
        extras={}
    )
    ex = FlowOpExecutor(ctx, on_status=ctx_base["on_status"])

    # 1) попытка /targetnext
    _send_chat(ex, "/targetnext", wait_ms=500)
    if _has_target_selected(win, server, lang):
        ctx_base["on_status"]("[AF boh] цель получена /targetnext", True)
        ok = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
        _RESTART_STREAK = 0 if ok else _RESTART_STREAK
        return ok

    # 2) перебор /target <имя из зоны>
    zone_id = (cfg or {}).get("zone") or ""
    names = _zone_monster_display_names(server, zone_id, lang)
    if not names:
        ctx_base["on_status"]("[AF boh] нет списка монстров зоны", False)
        return False

    for nm in names:
        _send_chat(ex, f"/target {nm}", wait_ms=500)
        if _has_target_selected(win, server, lang):
            ctx_base["on_status"](f"[AF boh] цель найдена: {nm}", True)
            ok = _attack_cycle(ex, ctx_base, server, lang, win, cfg)
            _RESTART_STREAK = 0 if ok else _RESTART_STREAK
            return ok

    # 3) не нашли цель — локальный перезапуск прохода
    _RESTART_STREAK += 1
    ctx_base["on_status"](f"[AF boh] цель не найдена, рестарт цикла #{_RESTART_STREAK}", None)
    if _RESTART_STREAK >= _RESTART_STREAK_LIMIT:
        ctx_base["on_status"]("[AF boh] 10 безрезультатных циклов → запустить ПОЛНЫЙ ЦИКЛ (как после смерти)", False)
        # тут просто возвращаем False; внешний оркестратор решит, что делать дальше (рестарт/в деревню и т.п.)
        return False
    return True

def _attack_cycle(ex: FlowOpExecutor, ctx_base: Dict[str, Any], server: str, lang: str,
                  win: Dict, cfg: Dict[str, Any]) -> bool:
    """
    Запускаем «движок атаки» выбранными скиллами.
    Правила:
      - круг завершается, когда каждый скилл был использован >=1 раза;
      - приоритет: скилл, который ещё не юзали в этом круге и уже вышел из cd,
        иначе любой готовый;
      - готовность определяем по elapsed >= cast_ms;
      - цель жива/мертва — по полосе HP в target-зоне (fallback: исчезновение target_init).
    """
    skills = list((cfg or {}).get("skills") or [])
    if not skills:
        ctx_base["on_status"]("[AF boh] нет настроенных скиллов", False)
        return False

    # нормализуем
    plan: List[Dict[str, Any]] = []
    now = time.time()
    for s in skills:
        k = str(s.get("key") or "1")
        cd = max(1, int(s.get("cast_ms") or 500)) / 1000.0
        plan.append({"key": k, "cd": cd, "last": 0.0, "used": False})

    start_ts = time.time()
    hard_timeout = 45.0  # страховка, чтобы не залипнуть бесконечно

    def ready(item) -> bool:
        return (time.time() - (item["last"] or 0.0)) >= item["cd"]

    # цикл до смерти цели или до завершения круга
    while True:
        if (time.time() - start_ts) > hard_timeout:
            ctx_base["on_status"]("[AF boh] таймаут атаки", False)
            return False

        # alive? (основной способ)
        alive = _target_alive_by_hp(win, server)
        if alive is False:
            ctx_base["on_status"]("[AF boh] цель мертва", True)
            return True
        if alive is None:
            # не смогли определить по цветам — fallback по шаблону
            if not _has_target_selected(win, server, lang):
                ctx_base["on_status"]("[AF boh] цель исчезла", True)
                return True

        # выберем скилл: сначала из "ещё не юзали в круге и готов", иначе любой готовый
        candidate = None
        for it in plan:
            if (not it["used"]) and ready(it):
                candidate = it; break
        if not candidate:
            ready_any = [it for it in plan if ready(it)]
            candidate = ready_any[0] if ready_any else None

        if candidate:
            if _press_key(ex, candidate["key"]):
                candidate["last"] = time.time()
                candidate["used"] = True
                # микропаузa, чтобы не зафлудить
                time.sleep(0.05)
        else:
            # ничего не готово — короткий sleep
            time.sleep(0.05)

        # завершение круга: все были использованы хотя бы раз
        if all(it["used"] for it in plan):
            ctx_base["on_status"]("[AF boh] круг скиллов завершён", True)
            return True
