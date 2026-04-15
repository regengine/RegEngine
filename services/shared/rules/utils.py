"""Utility functions for rule evaluation."""

from typing import Any, Dict


def get_nested_value(data: Dict[str, Any], field_path: str) -> Any:
    """Get a value from a nested dict using dot notation. e.g., 'kdes.harvest_date'."""
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current
