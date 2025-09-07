# _archive/core/features/post_tp_row.py
from __future__ import annotations
import importlib, time
from typing import Callable, Optional, Dict, List, Any, Tuple
from _archive.core.runtime.flow_ops import FlowCtx, FlowOpExecutor, run_flow

class PostTPRowRunner:
    def __init__(self, controller, server: str, get_window, get_language,
                 on_status: Callable[[str, Optional[bool]], None] = lambda *_: None,
                 on_finished: Callable[[], None] = lambda: None):
        self.controller = controller
        self.server = server
        self.get_window = get_window
        self.get_language = get_language
        self._on_status = on_status
        self._on_finished = on_finished   # ← NEW

    def set_server(self, server: str): self.server = server

    def run_row(self, village_id: str, location_id: str, row_id: str) -> bool:
        try:
            zones_mod = importlib.import_module(f"core.servers.{self.server}.zones.rows")
            zones = getattr(zones_mod, "ZONES", {})
            templates = getattr(zones_mod, "TEMPLATES", {})
        except Exception:
            zones, templates = {}, {}

        mod_path = f"core.servers.{self.server}.flows.rows.{village_id}.{location_id}.{row_id}"
        try:
            flow_mod = importlib.import_module(mod_path)
            flow = getattr(flow_mod, "FLOW", None)
        except Exception as e:
            self._on_status(f"[rows] flow load error: {e}", False)
            return False
        if not flow:
            self._on_status("[rows] flow missing", False)
            return False

        ctx = FlowCtx(
            server=self.server,
            controller=self.controller,
            get_window=self.get_window,
            get_language=self.get_language,
            zones=zones,
            templates=templates,
            extras={},
        )
        execu = FlowOpExecutor(ctx, on_status=self._on_status, logger=lambda m: print(m))
        try:
            return run_flow(flow, execu)
        finally:
            try:
                self._on_finished()   # ← вызов по окончании маршрута (успех/фейл — не важно)
            except Exception:
                pass

class RowsController:
    """
    Управляет списком маршрутов (rows) после ТП:
      - следит за сменой (cat, loc)
      - подгружает list_rows() из core.servers.<server>.flows.rows.registry
      - обновляет UI через коллбэки
    """

    def __init__(
        self,
        *,
        get_server: Callable[[], str],
        get_language: Callable[[], str],
        get_destination: Callable[[], Tuple[str, str]],  # (cat, loc)
        schedule: Callable[[Callable, int], None],        # schedule(fn, delay_ms)
        on_values: Callable[[List[Tuple[str, str]]], None],  # called with [(row_id, title)]
        on_select_row_id: Callable[[str], None],          # push selected row_id to TP UI
        log=print,
    ):
        self.get_server = get_server
        self.get_language = get_language
        self.get_destination = get_destination
        self._schedule = schedule
        self._on_values = on_values
        self._on_select_row_id = on_select_row_id
        self._log = log

        self._last_dest = ("", "")
        self._rows_cache: List[Tuple[str, str]] = []  # [(id, title)]
        self._list_rows_fn = None

    def start(self):
        self._schedule(self._watch, 200)

    # --- internals ---
    def _load_list_rows(self):
        server = self.get_server()
        try:
            mod = importlib.import_module(f"core.servers.{server}.flows.rows.registry")
            fn = getattr(mod, "list_rows", None)
            if callable(fn):
                return fn
        except Exception as e:
            self._log(f"[rows] resolver load error: {e}")
        return lambda *_: []

    def _watch(self):
        dest = self.get_destination()
        if dest != self._last_dest:
            self._last_dest = dest
            self._reload_rows()
        self._schedule(self._watch, 400)

    def _reload_rows(self):
        cat, loc = self._last_dest
        rows = []
        try:
            self._list_rows_fn = self._list_rows_fn or self._load_list_rows()
            if cat and loc:
                rows = self._list_rows_fn(cat, loc) or []
        except Exception as e:
            self._log(f"[rows] fetch error: {e}")
            rows = []

        lang = (self.get_language() or "rus").lower()

        def title_of(r):
            if lang == "rus":
                return r.get("title_rus") or r.get("id")
            return r.get("title_eng") or r.get("title_rus") or r.get("id")

        self._rows_cache = [(r["id"], title_of(r)) for r in rows if r.get("id")]
        self._on_values(self._rows_cache)

        # автоустановить первый валидный, если текущего нет
        if self._rows_cache:
            first_id = self._rows_cache[0][0]
            self._on_select_row_id(first_id)
        else:
            self._on_select_row_id("")
