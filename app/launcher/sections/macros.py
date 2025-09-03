# app/launcher/sections/macros.py
from __future__ import annotations
from ..base import BaseSection
from core.features.afterbuff_macros import AfterBuffMacroRunner

class MacrosSection(BaseSection):
    def __init__(self, window, controller, sys_state):
        super().__init__(window, sys_state)
        self.runner = AfterBuffMacroRunner(
            controller=controller,
            get_sequence=lambda: self.s.get("macros_sequence", ["1"]),
            get_delay_s=lambda: float(self.s.get("macros_delay_s", 1.0)),
        )

    def macros_set_enabled(self, enabled: bool): self.s["macros_enabled"] = bool(enabled)
    def macros_set_run_always(self, enabled: bool): self.s["macros_run_always"] = bool(enabled)
    def macros_set_delay(self, seconds: float): self.s["macros_delay_s"] = max(0.0, float(seconds or 0))
    def macros_set_duration(self, seconds: float): self.s["macros_duration_s"] = max(0.0, float(seconds or 0))
    def macros_set_sequence(self, seq): self.s["macros_sequence"] = [c for c in (seq or []) if c and c[0] in "0123456789"] or ["1"]

    def macros_run_once(self) -> bool:
        ok = self.runner.run_once()
        self.emit("macros", "Макросы выполнены" if ok else "Макросы не выполнены", ok)
        return bool(ok)

    def expose(self) -> dict:
        return {
            "macros_set_enabled": self.macros_set_enabled,
            "macros_set_run_always": self.macros_set_run_always,
            "macros_set_delay": self.macros_set_delay,
            "macros_set_duration": self.macros_set_duration,
            "macros_set_sequence": self.macros_set_sequence,
            "macros_run_once": self.macros_run_once,
        }
