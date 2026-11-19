"""Main app redirect for test imports.

Tests import 'from main import app', but actual file is app/main.py.
This file provides backward compatibility.
"""

from services.graph.app.main import app

__all__ = ["app"]
