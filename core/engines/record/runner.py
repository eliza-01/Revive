# core/engines/record/runner.py
from __future__ import annotations
from typing import Any, Dict, List

from core.state.pool import pool_get, pool_write
from core.logging import console

from .engine import RecordEngine

# Зарезервированные имена/слаги, которые нельзя использовать как записи
RESERVED_SLUGS = {"prefs"}


def _is_reserved_slug(slug: str) -> bool:
    return str(slug or "").strip().lower() in RESERVED_SLUGS


def _filter_records(recs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Убираем из списка любые записи с зарезервированными слагами."""
    out: List[Dict[str, str]] = []
    for r in (recs or []):
        try:
            if _is_reserved_slug(r.get("slug", "")):
                continue
            out.append(r)
        except Exception:
            # на всякий — пропустим битые элементы
            pass
    return out


class RecordRunner:
    """
    Координатор движка Record:
      - держит экземпляр RecordEngine
      - предоставляет API для хоткеев (Ctrl+R) и UI-кнопок ("создать", "запустить сейчас")
      - синхронизирует пул (records/current_record)
    """
    def __init__(self, state: Dict[str, Any], controller, get_window):
        self.state = state
        self.controller = controller
        self.get_window = get_window
        self.engine = RecordEngine(state, controller, get_window)

        # первичная синхронизация списка записей в пул
        self.sync_records_to_pool()

    # ---- pool sync ----

    def sync_records_to_pool(self):
        raw = self.engine.list_records()
        recs = _filter_records(raw)
        pool_write(self.state, "features.record", {"records": recs})
        console.log(f"[record.runner] synced {len(recs)} record(s) from disk (filtered)")

        cur = str(pool_get(self.state, "features.record.current_record", "") or "")
        # если в пуле лежит зарезервированное/невалидное — заменить
        valid_slugs = {r["slug"] for r in recs}
        if _is_reserved_slug(cur) or (cur and cur not in valid_slugs):
            cur = ""

        if not cur and recs:
            pool_write(self.state, "features.record", {"current_record": recs[0]["slug"]})

    # ---- API для UI ----

    def create_record(self, name: str) -> str:
        nm = str(name or "").strip()
        if not nm:
            raise ValueError("empty_name")
        # запрет на имя "prefs"
        if nm.lower() == "prefs":
            raise ValueError("reserved_name")

        _name, slug = self.engine.create_record(nm)

        # страховка: если вдруг движок вернул зарезервированный slug — не принимаем
        if _is_reserved_slug(slug):
            raise ValueError("reserved_name")

        # пересинхронизируем список (он уже будет отфильтрован)
        self.sync_records_to_pool()
        console.hud("ok", f"[record] создана запись: {nm}")
        console.log(f"[record.runner] create_record -> slug={slug}")
        return slug

    def play_now(self):
        try:
            pool_write(self.state, "features.record", {"enabled": True})
            console.log("[record.runner] play_now -> enabled=True")
        except Exception:
            pass

    def set_current(self, slug: str):
        try:
            if _is_reserved_slug(slug):
                return
            pool_write(self.state, "features.record", {"current_record": slug})
        except Exception:
            pass

    # ---- хоткей Ctrl+R ----

    def handle_hotkey(self, key: str):
        console.log(f"[record.runner] hotkey: {key}")
        if str(key).lower() not in ("ctrlr", "ctrl+r"):
            return
        status = str(pool_get(self.state, "features.record.status", "") or "")
        console.log(f"[record.runner] current status={status}")
        if status == "recording":
            if self.engine.stop_recording():
                console.hud("ok", "[record] запись остановлена")
                console.log("[record.runner] stop_recording -> ok")
            return
        self.engine.start_recording(countdown_s=0.0)
        console.log("[record.runner] start_recording -> requested")
