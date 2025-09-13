# core/engines/record/engine.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Optional
import os, json, time, threading, re

from core.logging import console
from core.state.pool import pool_get, pool_write
import traceback

Point = Tuple[int, int]

# ====== utils: storage & slug ======

def _records_dir() -> str:
    # Пользовательская директория (переживает компиляцию/обновления)
    base = os.path.expanduser("~/.revive/records")
    os.makedirs(base, exist_ok=True)
    return base

_RU2EN = {
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y",
    "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
    "х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
}
def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = "".join(_RU2EN.get(ch, ch) for ch in s)          # транслит ru->en
    s = re.sub(r"[^a-z0-9]+", "_", s)                    # не [a-z0-9] -> _
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "record"

def _unique_slug(base: str) -> str:
    d = _records_dir()
    slug = base
    i = 1
    while os.path.isfile(os.path.join(d, f"{slug}.json")):
        i += 1
        slug = f"{base}_{i}"
    return slug

def _now() -> float:
    return time.time()

def _client_xy(win: Dict[str, Any], sx: int, sy: int) -> Point:
    try:
        return int(sx - int(win.get("x", 0))), int(sy - int(win.get("y", 0)))
    except Exception:
        return int(sx), int(sy)


class RecordEngine:
    """
    Запись/воспроизведение действий мыши в координатах клиентского окна.
    - ЛКМ: фиксируем точку клика (client x,y) + t
    - ПКМ: пишем траекторию path каждые 30мс между press/release + t(момент press) + dt
    - Колёсико: wheel_up / wheel_down + t
    Воспроизведение: жёсткая синхронизация по t; движение — controller.move(),
    кнопки/колесо — Arduino (send).
    """

    # частота записи и сглаживания
    SAMPLE_DT = 0.008  # 30 ms между сэмплами
    FORMAT_VERSION = 2
    CLICK_AFTER_MOVE_S = 0.150

    # сгущение записи и сглаживание воспроизведения
    MIN_SAMPLE_DIST = 2  # px: брать точку, даже если таймер ещё не тикнул
    PIX_STEP = 2  # px: длина микрошага при интерполяции

    def __init__(self, state: Dict[str, Any], controller: Any, get_window):
        self.s = state
        self.controller = controller
        self.get_window = get_window

        # runtime
        self._recording = False
        self._playing = False
        self._busy_lock = threading.Lock()

        self._rec_name: str = ""
        self._rec_slug: str = ""
        self._rec_started_ts: float = 0.0
        self._t0: float = 0.0               # абсолютное время старта записи
        self._events: List[Dict[str, Any]] = []

        # RMB drag capture
        self._r_down = False
        self._r_path: List[Point] = []
        self._last_sample_ts: float = 0.0
        self._r_start_abs_t: float = 0.0    # абсолютное время R-press

        self._last_sample_pos: Optional[Point] = None  # для дистанционного триггера записи
    # -------- pool helpers --------
    MV_CHUNK = 1  # максимальная дельта за один HID-шаг
    SNAP_CURSOR_AFTER_RDRAG = True  # после ПКМ-драга вернуть курсор в записанную конечную точку

    def _send_mv_rel(self, dx: int, dy: int):
        """Относительное движение через прошивку: 'mv dx dy', с разбиением на мелкие шаги."""
        try:
            dx = int(dx);
            dy = int(dy)
            while dx != 0 or dy != 0:
                stepx = max(-self.MV_CHUNK, min(self.MV_CHUNK, dx))
                stepy = max(-self.MV_CHUNK, min(self.MV_CHUNK, dy))
                self.controller.send(f"mv {stepx} {stepy}")
                dx -= stepx;
                dy -= stepy
        except Exception:
            pass
    def _set_busy(self, val: bool):
        try:
            pool_write(self.s, "features.record", {"busy": bool(val), "ts": _now()})
        except Exception:
            pass

    def _set_status(self, status: str):
        try:
            pool_write(self.s, "features.record", {"status": status, "ts": _now()})
        except Exception:
            pass

    def _append_record_to_pool(self, name: str, slug: str):
        try:
            recs: List[Dict[str, str]] = list(pool_get(self.s, "features.record.records", []) or [])
            if not any(r.get("slug") == slug for r in recs):
                recs.append({"name": name, "slug": slug})
            pool_write(self.s, "features.record", {"records": recs, "current_record": slug})
        except Exception:
            pass

    # -------- persistence --------

    def list_records(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        d = _records_dir()
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(".json"):
                continue
            path = os.path.join(d, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    meta = json.load(f) or {}
                name = str(meta.get("name") or os.path.splitext(fn)[0])
                slug = str(meta.get("slug") or os.path.splitext(fn)[0])
                out.append({"name": name, "slug": slug})
            except Exception:
                continue
        return out

    def create_record(self, name: str) -> Tuple[str, str]:
        base = _slugify(name)
        slug = _unique_slug(base)
        data = {
            "name": name,
            "slug": slug,
            "created_ts": _now(),
            "steps": [],
            "version": self.FORMAT_VERSION,
        }
        path = os.path.join(_records_dir(), f"{slug}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self._append_record_to_pool(name, slug)
        return name, slug

    def _save_current_record(self):
        if not self._rec_slug:
            return
        path = os.path.join(_records_dir(), f"{self._rec_slug}.json")
        try:
            data = {
                "name": self._rec_name or self._rec_slug,
                "slug": self._rec_slug,
                "created_ts": self._rec_started_ts or _now(),
                "steps": self._events,
                "version": self.FORMAT_VERSION,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            console.log(f"[record] save error: {e}")

    # -------- recording API --------

    def start_recording(self, *, name: Optional[str] = None, countdown_s: float = 0.0):
        if self._recording or self._playing:
            return False

        # Получить/создать current_record
        slug = str(pool_get(self.s, "features.record.current_record", "") or "")
        if not slug:
            nm = name or "Новая запись"
            _name, slug = self.create_record(nm)
            self._rec_name = _name
        else:
            self._rec_name = slug
            for r in (pool_get(self.s, "features.record.records", []) or []):
                if r.get("slug") == slug:
                    self._rec_name = r.get("name") or slug
                    break

        # необязательный отсчёт до старта записи (не влияет на t)
        if countdown_s and countdown_s > 0:
            for i in range(int(countdown_s), 0, -1):
                console.hud("att", f"Запись начнётся через {i}")
                time.sleep(1.0)

        self._rec_slug = slug
        self._rec_started_ts = _now()
        self._t0 = self._rec_started_ts

        self._events = []
        self._r_down = False
        self._r_path = []
        self._last_sample_ts = 0.0
        self._r_start_abs_t = 0.0

        self._set_busy(True)
        self._set_status("recording")
        self._recording = True
        console.hud("att", "Запись началась 🔴")
        console.log(f"[record.engine] recording started slug={self._rec_slug}")
        return True

    def stop_recording(self):
        if not self._recording:
            return False
        if self._r_down and self._r_path:  # завершить незакрытый drag
            self._finalize_rdrag()
        self._save_current_record()
        self._recording = False
        self._set_status("idle")
        self._set_busy(False)
        console.hud("att", "")
        console.log(f"[record.engine] recording stopped and saved steps={len(self._events)}")
        return True

    # -------- playback API --------

    def play(self, slug: Optional[str] = None, *, wait_focus_cb=None, countdown_s: float = 1) -> bool:
        if self._recording or self._playing:
            return False

        target_slug = slug or str(pool_get(self.s, "features.record.current_record", "") or "")
        if not target_slug:
            console.hud("err", "[record] нет выбранной записи")
            return False

        path = os.path.join(_records_dir(), f"{target_slug}.json")
        if not os.path.isfile(path):
            console.hud("err", "[record] файл записи не найден")
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            steps: List[Dict[str, Any]] = list(data.get("steps") or [])
        except Exception as e:
            console.hud("err", f"[record] ошибка чтения: {e}")
            return False

        # жёстко требуем t у всех событий — без фолбэков
        if not steps or any("t" not in ev for ev in steps):
            console.hud("err", "[record] запись старого формата (нет t)")
            return False

        if callable(wait_focus_cb):
            ok = bool(wait_focus_cb(timeout_s=6.0))
            if not ok:
                console.hud("err", "[record] окно без фокуса")
                return False

        for i in range(int(countdown_s or 0), 0, -1):
            console.hud("att", f"Воспроизведение записи через {i}")
            time.sleep(1.0)
        console.hud("att", "")

        self._set_busy(True)
        self._set_status("playing")
        self._playing = True
        try:
            self._play_steps(steps)
            return True
        finally:
            self._playing = False
            self._set_status("idle")
            self._set_busy(False)

    def _play_steps(self, steps: List[Dict[str, Any]]):
        win = self.get_window() or {}
        x0 = int(win.get("x", 0));
        y0 = int(win.get("y", 0))

        def _move_client(cx: int, cy: int):
            # оставляем для одиночных кликов — позиционирование до клика
            try:
                self.controller.move(x0 + int(cx), y0 + int(cy))
            except Exception:
                pass

        def _send(cmd: str):
            try:
                self.controller.send(cmd)
            except Exception:
                pass

        events = sorted(steps, key=lambda e: float(e["t"]))
        start_wall = time.time()

        for ev in events:
            t_target = float(ev["t"])
            now_elapsed = time.time() - start_wall
            delay = t_target - now_elapsed
            if delay > 0:
                time.sleep(delay)

            typ = ev.get("type")

            if typ == "lclick":
                cx, cy = int(ev["x"]), int(ev["y"])
                _move_client(cx, cy)
                time.sleep(self.CLICK_AFTER_MOVE_S)  # небольшая пауза перед кликом
                _send("l")


            elif typ == "rdrag":

                path = list(ev.get("path") or [])

                dt = float(ev["dt"])

                if len(path) < 2:
                    continue

                mv_gain = float(pool_get(self.s, "features.record.mv_gain", 1.0))

                # Важно: не позиционируем курсор абсолютом в path[0]

                _send("R-press")

                prevx, prevy = int(path[0][0]), int(path[0][1])

                for (cx, cy) in path[1:]:

                    cx = int(cx);
                    cy = int(cy)

                    dx = int(round((cx - prevx) * mv_gain))

                    dy = int(round((cy - prevy) * mv_gain))

                    if dx or dy:
                        self._send_mv_rel(dx, dy)

                    prevx, prevy = cx, cy

                    if dt > 0:
                        time.sleep(dt)

                _send("R-release")

                # Чтобы визуально курсор оказался там же, где был в записи (только после отпускания ПКМ)

                if self.SNAP_CURSOR_AFTER_RDRAG:
                    endx, endy = int(path[-1][0]), int(path[-1][1])

                    _move_client(endx, endy)

            elif typ == "wheel_up":
                _send("wheel_up")
            elif typ == "wheel_down":
                _send("wheel_down")

    # -------- event feed (to be called by input layer) --------

    def on_mouse_left_click(self, screen_x: int, screen_y: int):
        if not self._recording:
            return
        win = self.get_window() or {}
        cx, cy = _client_xy(win, screen_x, screen_y)
        self._events.append({
            "type": "lclick",
            "x": int(cx), "y": int(cy),
            "t": round(_now() - self._t0, 4),
        })
        console.log(f"[record.engine] lclick at ({cx},{cy})")

    def on_mouse_right_press(self, screen_x: int, screen_y: int):
        if not self._recording:
            return
        self._r_down = True
        self._r_path = []
        self._last_sample_ts = 0.0
        self._r_start_abs_t = _now()
        self._sample_move(screen_x, screen_y, force=True)
        self._last_sample_pos = None

    def on_mouse_move(self, screen_x: int, screen_y: int):
        if not self._recording or not self._r_down:
            return
        self._sample_move(screen_x, screen_y, force=False)

    def on_mouse_right_release(self, screen_x: int, screen_y: int):
        if not self._recording or not self._r_down:
            return
        self._sample_move(screen_x, screen_y, force=True)
        self._finalize_rdrag()
        self._r_down = False

    def on_wheel_up(self):
        if not self._recording:
            return
        self._events.append({"type": "wheel_up", "t": round(_now() - self._t0, 4)})
        console.log("[record.engine] wheel_up")

    def on_wheel_down(self):
        if not self._recording:
            return
        self._events.append({"type": "wheel_down", "t": round(_now() - self._t0, 4)})
        console.log("[record.engine] wheel_down")

    def _move_rel(self, dx: int, dy: int):
        try:
            self.controller.move_rel(int(dx), int(dy))
        except Exception:
            pass

    def _r_down(self):
        try:
            self.controller.r_down()
        except Exception:
            pass

    def _r_up(self):
        try:
            self.controller.r_up()
        except Exception:
            pass

    def _smooth_rel_segment(self, x1: int, y1: int, x2: int, y2: int, total_dt: float, pix_step: int = 2):
        dx = x2 - x1
        dy = y2 - y1
        dist = max(abs(dx), abs(dy))
        steps = max(1, int(dist / max(1, pix_step)))
        sub_dt = (total_dt / steps) if total_dt > 0 else 0.0
        # равномерная линейная интерполяция, но отправляем ИМЕННО относительные дельты
        prev_x, prev_y = x1, y1
        for k in range(1, steps + 1):
            nx = int(round(x1 + dx * (k / steps)))
            ny = int(round(y1 + dy * (k / steps)))
            ddx = nx - prev_x
            ddy = ny - prev_y
            if ddx or ddy:
                self._move_rel(ddx, ddy)
            prev_x, prev_y = nx, ny
            if sub_dt > 0:
                time.sleep(sub_dt)
    # -------- internals --------

    def _move_client(self, cx: int, cy: int):
        win = self.get_window() or {}
        x0 = int(win.get("x", 0));
        y0 = int(win.get("y", 0))
        try:
            self.controller.move(x0 + int(cx), y0 + int(cy))
        except Exception:
            pass

    def _move_segment_smooth(self, x1: int, y1: int, x2: int, y2: int, total_dt: float):
        """Линейная интерполяция от (x1,y1) к (x2,y2) с шагом PIX_STEP и равномерной задержкой."""
        dx, dy = (x2 - x1), (y2 - y1)
        dist = max(abs(dx), abs(dy))
        steps = max(1, int(dist / self.PIX_STEP))
        # равномерная растяжка времени: суммарно total_dt на сегмент
        sub_dt = total_dt / steps if total_dt > 0 else 0.0

        for k in range(1, steps + 1):
            x = int(round(x1 + dx * (k / steps)))
            y = int(round(y1 + dy * (k / steps)))
            self._move_client(x, y)
            if sub_dt > 0:
                time.sleep(sub_dt)

    def _sample_move(self, sx: int, sy: int, *, force: bool):
        now = _now()
        win = self.get_window() or {}
        cx, cy = _client_xy(win, sx, sy)

        # по времени
        by_time = (now - self._last_sample_ts) >= self.SAMPLE_DT
        # по расстоянию
        if self._last_sample_pos is None:
            dist_ok = True
        else:
            lx, ly = self._last_sample_pos
            dx, dy = (cx - lx), (cy - ly)
            dist_ok = (dx*dx + dy*dy) >= (self.MIN_SAMPLE_DIST * self.MIN_SAMPLE_DIST)

        if force or by_time or dist_ok:
            self._r_path.append((int(cx), int(cy)))
            self._last_sample_ts = now
            self._last_sample_pos = (int(cx), int(cy))

    def _finalize_rdrag(self):
        if not self._r_path:
            return
        self._events.append({
            "type": "rdrag",
            "path": self._r_path[:],
            "dt": self.SAMPLE_DT,
            "t": round((self._r_start_abs_t or _now()) - self._t0, 4),
        })
        console.log(f"[record.engine] rdrag captured, points={len(self._r_path)}")
        self._r_path.clear()
        self._last_sample_pos = None
        self._r_start_abs_t = 0.0