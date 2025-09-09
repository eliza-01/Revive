from __future__ import annotations
from typing import Any, Dict

def expose_api(window, api: Dict[str, Any]) -> None:
    """
    Аккуратно экспонирует dict функций в pywebview так,
    чтобы имена в JS совпадали с ключами словаря.
    """
    wrappers = []
    for name, fn in api.items():
        def make_wrap(_fn, _name):
            def _w(*a, **kw):
                return _fn(*a, **kw)
            _w.__name__ = _name
            return _w
        wrappers.append(make_wrap(fn, name))
    window.expose(*wrappers)
