# app/controllers/rows_controller.py
from __future__ import annotations
import importlib
from typing import Callable, List, Tuple


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
