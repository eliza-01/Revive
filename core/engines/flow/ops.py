# core/engines/flow/ops.py
from __future__ import annotations

import time
import re
from typing import Callable, Dict, List, Optional, Tuple, Sequence, Any

from core.engines.flow.engine import FlowEngine
from core.vision.matching.template_matcher_2 import match_key_in_zone_single
from core.logging import console

# ---- logging toggle for ops ----
OPS_LOGGING: bool = False

def _ops_log(msg: str) -> None:
    if OPS_LOGGING:
        try:
            console.log(str(msg))
        except Exception:
            pass

_RU2US = {
    # верхний ряд
    "й":"q","ц":"w","у":"e","к":"r","е":"t","н":"y","г":"u","ш":"i","щ":"o","з":"p","х":"[","ъ":"]",
    # средний
    "ф":"a","ы":"s","в":"d","а":"f","п":"g","р":"h","о":"j","л":"k","д":"l","ж":";","э":"'",
    # нижний
    "я":"z","ч":"x","с":"c","м":"v","и":"b","т":"n","ь":"m","б":",","ю":".","ё":"`",
    # прочее
    " ":" ","-":"-",
}
_SHIFT_PUNCT = {"[":"{","]":"}",";":":","'":'"',",":"<",".":">","`":"~"}

def _ru_to_us_keys(text: str) -> str:
    out = []
    for ch in text:
        lo = ch.lower()
        if lo in _RU2US:
            key = _RU2US[lo]
            if ch.isupper():
                if "a" <= key <= "z":
                    out.append(key.upper())
                else:
                    out.append(_SHIFT_PUNCT.get(key, key))
            else:
                out.append(key)
        else:
            out.append(ch)  # оставить ASCII и прочее как есть
    return "".join(out)

ZoneLTRB = Tuple[int, int, int, int]

class FlowCtx:
    def __init__(
            self,
            server: str,
            controller,
            get_window: Callable[[], Optional[dict]],
            get_language: Callable[[], str],
            zones: Dict[str, object],
            templates: Dict[str, List[str]],
            extras: Optional[Dict[str, Any]] = None,
    ):
        self.server = server
        self.controller = controller
        self.get_window = get_window
        self.get_language = get_language
        self.zones = zones or {}
        self.templates = templates or {}
        self.extras = extras or {}

    def _lang(self) -> str:
        try:
            return (self.get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _win(self) -> Dict:
        return self.get_window() or {}

    def _zone_ltrb(self, zone_decl) -> ZoneLTRB:
        win = self._win()
        if isinstance(zone_decl, tuple) and len(zone_decl) == 4:
            return tuple(map(int, zone_decl))
        if isinstance(zone_decl, dict):
            ww, wh = int(win.get("width", 0)), int(win.get("height", 0))
            if zone_decl.get("fullscreen"):
                return (0, 0, ww, wh)
            if zone_decl.get("centered"):
                w, h = int(zone_decl["width"]), int(zone_decl["height"])
                l = ww // 2 - w // 2
                t = wh // 2 - h // 2
                return (l, t, l + w, t + h)

            # размеры: абсолют или доля
            w = int(ww * float(zone_decl["width_ratio"])) if "width_ratio" in zone_decl else int(zone_decl.get("width", 0))
            h = int(wh * float(zone_decl["height_ratio"])) if "height_ratio" in zone_decl else int(zone_decl.get("height", 0))

            # горизонталь: left_ratio | right_offset|right | left
            if "left_ratio" in zone_decl:
                l = int(ww * float(zone_decl["left_ratio"]))
            elif "right_offset" in zone_decl or "right" in zone_decl:
                ro = int(zone_decl.get("right_offset", zone_decl.get("right", 0)))
                l = ww - ro - w
            else:
                l = int(zone_decl.get("left", 0))

            # вертикаль: top_ratio | bottom_offset|bottom | top
            if "top_ratio" in zone_decl:
                t = int(wh * float(zone_decl["top_ratio"]))
            elif "bottom_offset" in zone_decl or "bottom" in zone_decl:
                bo = int(zone_decl.get("bottom_offset", zone_decl.get("bottom", 0)))
                t = wh - bo - h
            else:
                t = int(zone_decl.get("top", 0))

            return (l, t, l + w, t + h)

        return (0, 0, int(self._win().get("width", 0)), int(self._win().get("height", 0)))

    def _parts(self, tpl_key_or_parts: Sequence[str] | str) -> Optional[List[str]]:
        if isinstance(tpl_key_or_parts, str):
            return self.templates.get(tpl_key_or_parts)
        return list(tpl_key_or_parts or [])

    def wait(self, zone_key: str, tpl_key: str, timeout_ms: int, thr: float) -> bool:
        zone = self.zones.get(zone_key); parts = self._parts(tpl_key)
        if not zone or not parts:
            return False
        ltrb = self._zone_ltrb(zone); win = self._win()
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            if match_key_in_zone_single(
                    window=win,
                    zone_ltrb=ltrb,
                    server=self.server,
                    lang=self._lang(),
                    template_parts=parts,
                    threshold=thr,
                    engine="dashboard",
            ):
                return True
            time.sleep(0.05)
        return False

    def _click_in(self, zone_key: str, tpl_key_or_parts: Sequence[str] | str, timeout_ms: int, thr: float) -> bool:
        zone = self.zones.get(zone_key); parts = self._parts(tpl_key_or_parts)
        if not zone or not parts:
            return False
        ltrb = self._zone_ltrb(zone); win = self._win()
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            pt = match_key_in_zone_single(
                window=win,
                zone_ltrb=ltrb,
                server=self.server,
                lang=self._lang(),
                template_parts=parts,
                threshold=thr,
                engine="dashboard",
            )
            if pt:
                try:
                    self.controller.send(f"click:{pt[0]},{pt[1]}")
                except Exception:
                    pass
                time.sleep(0.08)
                return True
            time.sleep(0.05)
        return False

    def _visible(self, zone_key: str, tpl_key_or_parts, thr: float) -> bool:
        zone = self.zones.get(zone_key); parts = self._parts(tpl_key_or_parts)
        if not zone or not parts:
            return False
        ltrb = self._zone_ltrb(zone); win = self._win()
        return match_key_in_zone_single(
            window=win,
            zone_ltrb=ltrb,
            server=self.server,
            lang=self._lang(),
            template_parts=parts,
            threshold=thr,
            engine="dashboard",
        ) is not None


class FlowOpExecutor:
    def __init__(self, ctx: FlowCtx, logger: Callable[[str], None] = _ops_log):
        self.ctx = ctx
        self._log = logger

    def _subst(self, s: str) -> str:
        if not isinstance(s, str):
            return s
        extras = self.ctx.extras or {}
        acc = extras.get("account") or {}
        login = acc.get("login", "") or extras.get("account_login", "")
        pwd   = acc.get("password", "") or extras.get("account_password", "")

        # 1) спец-алиасы
        s = (s.replace("{account.login}", login)
               .replace("{account.password}", pwd)
               .replace("{account_login}", login)
               .replace("{account_password}", pwd))

        # 2) универсально: любые {key} → extras[key]
        def repl(m):
            k = m.group(1)
            return str(extras.get(k, m.group(0)))
        return re.sub(r"\{([A-Za-z0-9_]+)\}", repl, s)

    def exec(self, step: Dict, idx: int, total: int) -> bool:
        op = step.get("op"); thr = float(step.get("thr", 0.87))
        # безопасный лог: не светим 'text'
        safe_step = {k: v for k, v in step.items() if k != "text"}
        self._log(f"[flow][step {idx}/{total}] {op}: {safe_step}")

        try:
            if op == "wait":
                ok = self.ctx.wait(step["zone"], step["tpl"], int(step["timeout_ms"]), thr)

            elif op == "wait_optional":
                # Мягкое ожидание с внутренними ретраями
                zone = step["zone"]
                tpl  = step["tpl"]
                timeout_ms = int(step.get("timeout_ms", 2000))
                thr = float(step.get("thr", thr))
                retries = int(step.get("retry_count", 0))
                delay_ms = int(step.get("retry_delay_ms", 0))

                found = False
                total_tries = max(1, retries + 1)
                for attempt in range(total_tries):
                    if self.ctx.wait(zone, tpl, timeout_ms, thr):
                        found = True
                        break
                    if attempt < total_tries - 1 and delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)

                if not found:
                    self._log(f"[flow] wait_optional: '{tpl}' not found after {total_tries} tries → continue")
                ok = True

            elif op == "click_in":
                tpl = step["tpl"]
                if tpl == "{mode_key}":
                    tpl = self.ctx.extras.get("mode_key_provider", lambda: None)() or "buffer_mode_profile"
                ok = self.ctx._click_in(step["zone"], tpl, int(step["timeout_ms"]), thr)

            elif op == "click_any":
                ok = False
                deadline = time.time() + int(step["timeout_ms"]) / 1000.0
                while time.time() < deadline and not ok:
                    for zk in tuple(step["zones"]):
                        ok = self.ctx._click_in(zk, step["tpl"], 1, thr)
                        if ok:
                            break
                    time.sleep(0.05)

            elif op == "click_optional":
                # Мягкий клик с внутренними ретраями
                zone = step["zone"]
                tpl  = step["tpl"]
                if tpl == "{mode_key}":
                    tpl = self.ctx.extras.get("mode_key_provider", lambda: None)() or "buffer_mode_profile"

                timeout_ms = int(step.get("timeout_ms", 800))
                thr = float(step.get("thr", thr))
                retries = int(step.get("retry_count", 0))
                delay_ms = int(step.get("retry_delay_ms", 0))

                success = False
                total_tries = max(1, retries + 1)
                for attempt in range(total_tries):
                    if self.ctx._click_in(zone, tpl, timeout_ms, thr):
                        success = True
                        break
                    if attempt < total_tries - 1 and delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)

                if not success:
                    self._log(f"[flow] click_optional: '{tpl}' not clicked after {total_tries} tries → continue")
                ok = True

            elif op == "enter_pincode":
                # МЯГКИЙ PIN
                zone = step.get("zone", "fullscreen")
                visible_tpl = step.get("visible_tpl", "enter_pincode")
                if not self.ctx._visible(zone, visible_tpl, thr):
                    ok = True
                else:
                    acc = self.ctx.extras.get("account") or {}
                    pin = str(acc.get("pin") or self.ctx.extras.get("account_pin") or "")
                    if not pin:
                        ok = True
                    else:
                        digit_delay = int(step.get("digit_delay_ms", 120))
                        ok = True
                        for d in pin:
                            tpl_key = f"num{d}"
                            if not self.ctx._click_in(zone, tpl_key, int(step.get("timeout_ms", 1500)), thr):
                                ok = False
                                break
                            if digit_delay > 0:
                                time.sleep(digit_delay / 1000.0)

            elif op == "click_zone_center":
                zone_key = step["zone"]
                zone = self.ctx.zones.get(zone_key)
                if not zone:
                    ok = False
                else:
                    l, t, r, b = self.ctx._zone_ltrb(zone)
                    x = (l + r) // 2
                    y = (t + b) // 2
                    try:
                        self.ctx.controller.send(f"click:{x},{y}")
                    except Exception:
                        pass
                    time.sleep(int(step.get("delay_ms", 80)) / 1000.0)
                    ok = True

            elif op == "move_zone_center":
                zone_key = step["zone"]
                zone = self.ctx.zones.get(zone_key)
                if not zone:
                    ok = False
                else:
                    l, t, r, b = self.ctx._zone_ltrb(zone)
                    x = (l + r) // 2
                    y = (t + b) // 2
                    try:
                        self.ctx.controller.send(f"move:{x},{y}")
                    except Exception:
                        pass
                    time.sleep(int(step.get("delay_ms", 50)) / 1000.0)
                    ok = True

            elif op == "dashboard_is_locked":
                ok = self._dashboard_is_locked(step, thr)

            elif op == "while_visible_send":
                ok = self._while_visible_send(step, thr)

            elif op == "send_arduino":
                cmd = step.get("cmd", "")
                delay_ms = int(step.get("delay_ms", 100))
                count = int(step.get("count", 1))
                if count <= 0:
                    count = 1
                for i in range(count):
                    try:
                        self.ctx.controller.send(cmd)
                    except Exception:
                        pass
                    if delay_ms > 0 and i < count - 1:
                        time.sleep(delay_ms / 1000.0)
                ok = True

            elif op == "enter_text":
                text = self._subst(str(step.get("text", "")))
                layout = (step.get("layout") or "auto").lower()
                # если печатаем русское слово при RU-раскладке — конвертим
                if layout == "ru" or (layout == "auto" and any(ord(c) > 127 for c in text)):
                    text = _ru_to_us_keys(text)
                self.ctx.controller.send(f"enter_text {text}")
                ok = True

            elif op == "press_enter":
                self.ctx.controller.send("press_enter")
                ok = True

            elif op == "press_esc":
                self.ctx.controller.send("esc")
                ok = True

            elif op == "send_message":
                text = self._subst(str(step.get("text", "")))  # плейсхолдеры
                layout = (step.get("layout") or "auto").lower()
                if layout == "ru" or (layout == "auto" and any(ord(c) > 127 for c in text)):
                    text = _ru_to_us_keys(text)
                self.ctx.controller.send(f"enter {text}")
                ok = True

            elif op == "set_layout":
                # Только Alt+Shift
                target = (step.get("layout") or step.get("value") or "toggle").lower()  # "toggle" | "ru" | "en"
                count = int(step.get("count", 1))
                delay_ms = int(step.get("delay_ms", 120))

                def _toggle_once():
                    try:
                        self.ctx.controller.send("layout_toggle_altshift")
                    except Exception:
                        pass
                    if delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)

                cur = getattr(self, "_kb_layout", None)

                if target in ("toggle", "switch"):
                    if count <= 0:
                        count = 1
                    for _ in range(count):
                        _toggle_once()
                    ok = True
                elif target in ("ru", "en"):
                    if cur == target:
                        ok = True
                    else:
                        _toggle_once()
                        self._kb_layout = target
                        ok = True
                else:
                    self._log(f"[flow] set_layout: unknown layout '{target}'")
                    ok = False

            elif op == "sleep":
                time.sleep(int(step.get("ms", 50)) / 1000.0)
                ok = True

            elif op == "click_village":
                ok = self._click_by_resolver(step["zone"], "village_png", step, thr)

            elif op == "click_location":
                ok = self._click_by_resolver(step["zone"], "location_png", step, thr)

            else:
                self._log(f"[flow] unknown op: {op}")
                ok = False

        except Exception as e:
            self._log(f"[flow] op error {op}: {e}")
            ok = False

        # ЕДИНЫЙ ПОСТ-ОЖИДАТЕЛЬ ДЛЯ ЛЮБОГО ШАГА
        try:
            post_wait = int(step.get("wait_ms", 0))
        except Exception:
            post_wait = 0
        if post_wait > 0 and op != "sleep":
            time.sleep(post_wait / 1000.0)

        self._log(f"[flow][step {idx}] result: {'OK' if ok else 'FAIL'}")
        return ok

    def _dashboard_is_locked(self, step: Dict, thr: float) -> bool:
        zone_key = step["zone"]; tpl_key = step["tpl"]
        timeout_ms = int(step.get("timeout_ms", 12000)); interval_s = float(step.get("probe_interval_s", 1.0))
        start = time.time(); next_probe = 0.0
        while (time.time() - start) * 1000.0 < timeout_ms:
            if not self.ctx._visible(zone_key, tpl_key, thr):
                return True
            now = time.time()
            if now >= next_probe:
                try:
                    self.ctx.controller.send("l")
                except Exception:
                    pass
                next_probe = now + interval_s
            time.sleep(0.08)
        self._log("[flow] dashboard still locked")
        return False

    def _while_visible_send(self, step: Dict, thr: float) -> bool:
        """Пока виден tpl в zone — отправлять cmd (например, 'b')."""
        zone_key = step["zone"]; tpl_key = step["tpl"]
        cmd = step.get("cmd", "b")
        timeout_ms = int(step.get("timeout_ms", 10000)); interval_s = float(step.get("probe_interval_s", 0.5))
        start = time.time(); next_probe = 0.0
        while (time.time() - start) * 1000.0 < timeout_ms:
            if not self.ctx._visible(zone_key, tpl_key, thr):
                return True
            now = time.time()
            if now >= next_probe:
                try:
                    self.ctx.controller.send(cmd)
                except Exception:
                    pass
                next_probe = now + interval_s
            time.sleep(0.05)
        self._log(f"[flow] still visible: {tpl_key}")
        return False

    def _click_by_resolver(self, zone_key: str, which: str, step: Dict, thr: float) -> bool:
        resolver = self.ctx.extras.get("resolver")
        if not callable(resolver):
            return False

        lang = self.ctx._lang()
        cat = (self.ctx.extras.get("category_id") or "")
        loc = (self.ctx.extras.get("location_id") or "")

        # Hotspots не открывает «вилладж» (нет подменю)
        if which == "village_png" and (cat or "").lower() == "hotspots":
            return True

        if which == "village_png":
            if not cat:
                return False
            file = f"{cat}.png"
            ok_res = bool(resolver(lang, "dashboard", "teleport", "villages", cat, file))
            if not ok_res:
                self._log(f"[teleport] village template missing: {cat}")
                return False
            parts = ["dashboard", "teleport", "villages", cat, file]
        else:  # location_png
            if not (cat and loc):
                return False
            file = f"{loc}.png"
            ok_res = bool(resolver(lang, "dashboard", "teleport", "villages", cat, file))
            if not ok_res:
                self._log(f"[teleport] location template missing: {cat}/{loc}")
                return False
            parts = ["dashboard", "teleport", "villages", cat, file]

        return self.ctx._click_in(
            zone_key, parts,
            int(step.get("timeout_ms", 2500)),
            float(step.get("thr", 0.88)),
        )

    def _expand_text(self, text: str) -> str:
        if not isinstance(text, str):
            return text
        return re.sub(r"\{([A-Za-z0-9_]+)\}", lambda m: str(self.ctx.extras.get(m.group(1), "")), text)


def run_flow(flow: List[Dict], executor: FlowOpExecutor) -> bool:
    engine = FlowEngine(flow, executor.exec)
    return engine.run()
