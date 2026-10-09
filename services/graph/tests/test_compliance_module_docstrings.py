"""Docs regression test for the FSMA compliance router module.

Fails on code that removes the module or public class docstrings added to
close the 2026-10-08 docs gap on services/graph/app/routers/fsma/compliance.py.
"""

import ast
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "routers" / "fsma" / "compliance.py"

DOCUMENTED_CLASSES = {
    "CommodityRequest",
    "RecordLocationRequest",
    "TraceabilityPlanRequest",
    "ComplianceScoreResponse",
}


def _module_tree():
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def test_module_docstring_present():
    assert ast.get_docstring(_module_tree()), "compliance.py must have a module docstring"


def test_public_class_docstrings_present():
    tree = _module_tree()
    found = {node.name: ast.get_docstring(node) for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    for name in DOCUMENTED_CLASSES:
        assert found.get(name), f"{name} must have a class docstring"


def test_docstrings_use_plain_english():
    tree = _module_tree()
    texts = [ast.get_docstring(tree)] + [
        ast.get_docstring(node) for node in ast.walk(tree) if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    ]
    for text in texts:
        if not text:
            continue
        assert "\u2014" not in text and "\u2013" not in text, "docstrings must not use em or en dashes"
        assert "exactly-once" not in text.lower(), "docstrings must not claim exactly-once behavior"
