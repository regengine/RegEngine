"""Docstring coverage for the FSMA traceability router module."""

import ast
from pathlib import Path


def _module_node():
    path = Path(__file__).resolve().parents[1] / "app" / "routers" / "fsma" / "traceability.py"
    return ast.parse(path.read_text())


def test_module_has_docstring():
    assert ast.get_docstring(_module_node()), "module docstring is missing"


def test_public_classes_and_functions_have_docstrings():
    node = _module_node()
    missing = [
        n.name
        for n in node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not n.name.startswith("_")
        and not ast.get_docstring(n)
    ]
    assert not missing, f"missing docstrings: {missing}"
