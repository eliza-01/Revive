from __future__ import annotations
from typing import Any, Dict, Callable, List, Optional
import importlib

from core.logging import console


class PlayerStateRulesEngine:
    """
    Грузит server-specific правила PlayerState и отдаёт их как список объектов
    с интерфейсом rule.when(snap)->bool / rule.run(snap)->None.

    В rules.build_rules(state, helpers=...) передаём полезные коллбеки:
      helpers = {
        "ensure_ui_guard_runner": callable() -> Optional[Runner],
        "mask_vitals": callable() -> None,
        "hud": callable(kind: str, text: str) -> None,
      }

    Сигнатура build_rules может быть:
      - build_rules(state, helpers=...)
      - build_rules(state)                 (будет вызвана fallback'ом)
    """

    def __init__(
        self,
        *,
        state: Dict[str, Any],
        get_server: Callable[[], str],
        ensure_ui_guard_runner: Callable[[], Any],
        mask_vitals: Callable[[], None],
        hud: Callable[[str, str], None],
    ):
        self.s = state
        self._get_server = get_server
        self._ensure_ui_guard_runner = ensure_ui_guard_runner
        self._mask_vitals = mask_vitals
        self._hud = hud
        self._built: Optional[List[Any]] = None

    def _build_once(self) -> List[Any]:
        srv = (self._get_server() or "common").lower()
        mod_name = f"core.engines.player_state.server.{srv}.rules"
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            console.log(f"[ps.rules] module not found for server '{srv}': {mod_name}: {e}")
            return []

        if not hasattr(mod, "build_rules"):
            console.log(f"[ps.rules] 'build_rules(state, helpers=...)' missing in {mod_name}")
            return []

        helpers = {
            "ensure_ui_guard_runner": self._ensure_ui_guard_runner,
            "mask_vitals": self._mask_vitals,
            "hud": self._hud,
        }

        try:
            # сначала пробуем сигнатуру с helpers
            rules = mod.build_rules(self.s, helpers=helpers)  # type: ignore
        except TypeError:
            # fallback: старая сигнатура
            rules = mod.build_rules(self.s)  # type: ignore
        except Exception as e:
            console.log(f"[ps.rules] build_rules error: {e}")
            return []

        rules = list(rules or [])
        console.log(f"[ps.rules] loaded {len(rules)} rule(s) for server='{srv}'")
        return rules

    def get_rules(self) -> List[Any]:
        if self._built is None:
            self._built = self._build_once()
        return self._built
