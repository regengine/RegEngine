"""Docstring coverage for the LLM extractor module (docs gap found 2026-10-08).

Uses ``ast`` on the source file so the check needs no provider SDKs.
"""

import ast
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "app" / "extractors" / "llm_extractor.py"


def _load_tree():
    tree = ast.parse(MODULE_PATH.read_text())
    assert ast.get_docstring(tree), "module docstring is missing"
    return tree


def test_module_has_docstring():
    _load_tree()


def test_public_classes_and_functions_have_docstrings():
    tree = _load_tree()
    missing = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and not node.name.startswith("_"):
            if not ast.get_docstring(node):
                missing.append(node.name)
        if isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and not child.name.startswith("_"):
                    if not ast.get_docstring(child):
                        missing.append(f"{node.name}.{child.name}")
    assert not missing, f"missing docstrings: {missing}"
