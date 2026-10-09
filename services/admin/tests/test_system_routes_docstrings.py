"""Docstring coverage for services/admin/app/system_routes.py.

Regression coverage for the docs gap found 2026-10-08: the module had no
module docstring and several public classes and functions lacked one.
"""

import services.admin.app.system_routes as system_routes

DOCUMENTED_MODELS = (
    "ServiceHealth",
    "SystemStatusResponse",
    "SystemMetricsResponse",
    "TaskQueueSummaryResponse",
    "TaskQueueReplayRequest",
    "TaskQueueReplayResult",
    "TaskQueueReplayResponse",
)

DOCUMENTED_FUNCTIONS = ("get_system_status",)


def test_module_has_docstring() -> None:
    assert system_routes.__doc__, "system_routes needs a module docstring"


def test_public_models_have_docstrings() -> None:
    missing = [name for name in DOCUMENTED_MODELS if not getattr(system_routes, name).__doc__]
    assert not missing, f"these models lack docstrings: {missing}"


def test_public_handlers_have_docstrings() -> None:
    missing = [name for name in DOCUMENTED_FUNCTIONS if not getattr(system_routes, name).__doc__]
    assert not missing, f"these handlers lack docstrings: {missing}"


def test_new_docstrings_use_plain_english() -> None:
    objs = [system_routes] + [getattr(system_routes, name) for name in DOCUMENTED_MODELS + DOCUMENTED_FUNCTIONS]
    for obj in objs:
        text = obj.__doc__ or ""
        assert "\u2014" not in text, f"em dash in {obj!r} docstring"
        assert "\u2013" not in text, f"en dash in {obj!r} docstring"
        assert "exactly-once" not in text.lower(), f"banned claim in {obj!r} docstring"
