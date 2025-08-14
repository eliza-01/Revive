# core/checks/charged.py
from __future__ import annotations
import importlib
import time
from typing import Callable, Optional, Dict, List, Tuple

from core.vision.matching.template_matcher import match_in_zone

# ---------- базовый проб ----------
class Probe:
    def __init__(self, name: str):
        self.name = name
        self.enabled = True

    def set_enabled(self, v: bool): self.enabled = bool(v)
    def check(self) -> Optional[bool]:
        """Возвращает True/False, либо None при ошибке/нет данных."""
        raise NotImplementedError

# ---------- проб: иконки бафов по шаблонам ----------
class BuffTemplateProbe(Probe):
    """
    Видим хотя бы одну из иконок в заданной зоне → считаем 'заряжен'.
    Зоны/темплейты берём из core.servers.<server>.zones.buffs_state
    """
    def __init__(
            self,
            name: str,
            server_getter: Callable[[], str],
            get_window: Callable[[], Optional[Dict]],
            get_language: Callable[[], str],
            zone_key: str,
            tpl_keys: List[str],
            threshold: float = 0.83,
            debug: bool = False,
    ):
        super().__init__(name)
        self._get_server = server_getter
        self._get_window = get_window
        self._get_language = get_language
        self.zone_key = zone_key
        self.tpl_keys = list(tpl_keys)
        self.threshold = float(threshold)
        self.debug = bool(debug)

        self._zones: Dict[str, object] = {}
        self._templates: Dict[str, List[str]] = {}
        self._load_cfg()

    def _load_cfg(self):
        try:
            server = (self._get_server() or "l2mad").lower()
            mod = importlib.import_module(f"core.servers.{server}.zones.buffs_state")
            self._zones = getattr(mod, "ZONES", {})
            self._templates = getattr(mod, "TEMPLATES", {})
            if self.debug:
                print(f"[charged] probe '{self.name}': cfg loaded for {server}")
        except Exception as e:
            print(f"[charged] probe '{self.name}': cfg load error: {e}")
            self._zones, self._templates = {}, {}

    def _lang(self) -> str:
        try:
            return (self._get_language() or "rus").lower()
        except Exception:
            return "rus"

    def _zone_ltrb(self, win: Dict, zone_decl) -> Tuple[int,int,int,int]:
        if isinstance(zone_decl, tuple) and len(zone_decl) == 4:
            return tuple(map(int, zone_decl))
        if isinstance(zone_decl, dict):
            ww, wh = int(win.get("width", 0)), int(win.get("height", 0))
            if zone_decl.get("fullscreen"): return (0, 0, ww, wh)
            if zone_decl.get("centered"):
                w, h = int(zone_decl["width"]), int(zone_decl["height"])
                l, t = ww//2 - w//2, wh//2 - h//2
                return (l, t, l+w, t+h)
            l = int(zone_decl.get("left", 0)); t = int(zone_decl.get("top", 0))
            w = int(zone_decl.get("width", 0)); h = int(zone_decl.get("height", 0))
            return (l, t, l+w, t+h)
        return (0, 0, int(win.get("width", 0)), int(win.get("height", 0)))

    def _is_visible(self, win: Dict, zone_key: str, tpl_key: str, thr: float) -> bool:
        zone = self._zones.get(zone_key); parts = self._templates.get(tpl_key)
        if not zone or not parts: return False
        ltrb = self._zone_ltrb(win, zone)
        return match_in_zone(win, ltrb, (self._get_server() or "l2mad"), self._lang(), parts, thr) is not None

    def check(self) -> Optional[bool]:
        if not self.enabled: return None
        win = self._get_window() or {}
        if not win: return None
        # пробуем по списку иконок
        for key in self.tpl_keys:
            if self._is_visible(win, self.zone_key, key, self.threshold):
                if self.debug: print(f"[charged] probe '{self.name}': hit {key}")
                return True
        return False

# ---------- агрегатор ----------
class ChargeChecker:
    """
    Агрегирует несколько пробов. Режим: ANY (по умолчанию) или ALL.
    Имеет интервал опроса, внутренний кэш последнего результата.
    """
    def __init__(self, interval_minutes: int = 10, mode: str = "ANY"):
        self._probes: Dict[str, Probe] = {}
        self._enabled = True
        self._interval_s = max(1, int(interval_minutes) * 60)
        self._mode = "ALL" if str(mode).upper() == "ALL" else "ANY"
        self._last_ts = 0.0
        self._last_val: Optional[bool] = None

    # управление
    def set_enabled(self, v: bool): self._enabled = bool(v)
    def set_interval_minutes(self, m: int): self._interval_s = max(1, int(m) * 60)
    def set_mode_any(self): self._mode = "ANY"
    def set_mode_all(self): self._mode = "ALL"

    # пробы
    def register_probe(self, name: str, probe: Probe, enabled: bool = True):
        probe.set_enabled(enabled)
        self._probes[name] = probe

    def set_probe_enabled(self, name: str, v: bool):
        p = self._probes.get(name);
        if p: p.set_enabled(v)

    # ядро
    def _combine(self, results: List[bool]) -> Optional[bool]:
        if not results: return None
        if self._mode == "ANY": return any(results)
        return all(results)

    def _evaluate_now(self) -> Optional[bool]:
        vals: List[bool] = []
        for p in self._probes.values():
            try:
                r = p.check()
                if r is not None:
                    vals.append(bool(r))
            except Exception:
                # игнорим сбой одного проба
                pass
        return self._combine(vals)

    def tick(self) -> bool:
        """
        Вызывай хоть каждую секунду. Вернёт True, если значение изменилось.
        """
        if not self._enabled: return False
        now = time.time()
        if (now - self._last_ts) < self._interval_s:
            return False
        val = self._evaluate_now()
        changed = (val != self._last_val)
        self._last_val = val
        self._last_ts = now
        return changed

    def is_charged(self, _unused=None) -> Optional[bool]:
        """Текущее закэшированное значение, без форс-проверки."""
        return self._last_val

    def force_check(self) -> Optional[bool]:
        """Мгновенная проверка. Обновляет кэш."""
        val = self._evaluate_now()
        self._last_val = val
        self._last_ts = time.time()
        return val

    def invalidate(self) -> None:
        """Сбросить кеш и таймер, чтобы след. запрос не полагался на старое значение."""
        self._last_val = None
        self._last_ts = 0.0