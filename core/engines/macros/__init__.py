# core/engines/macros/__init__.py
from __future__ import annotations

# Упрощённый публичный API
from .runner import run_macros  # noqa: F401

__all__ = ["run_macros"]
