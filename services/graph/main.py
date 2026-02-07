"""Main app redirect for test imports.

Tests import 'from main import app', but actual file is app/main.py.
This file provides backward compatibility.
"""
from app.main import app

__all__ = ["app"]
