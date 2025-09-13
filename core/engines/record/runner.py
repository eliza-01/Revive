# core/engines/record/runner.py
from __future__ import annotations
from typing import Any, Dict

from core.state.pool import pool_get, pool_write
from core.logging import console

from .engine import RecordEngine

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
        recs = self.engine.list_records()
        pool_write(self.state, "features.record", {"records": recs})
        console.log(f"[record.runner] synced {len(recs)} record(s) from disk")
        cur = pool_get(self.state, "features.record.current_record", "") or ""
        if not cur and recs:
            pool_write(self.state, "features.record", {"current_record": recs[0]["slug"]})

    # ---- API для UI ----

    def create_record(self, name: str) -> str:
        _name, slug = self.engine.create_record(name)
        self.sync_records_to_pool()
        console.hud("ok", f"[record] создана запись: {name}")
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
