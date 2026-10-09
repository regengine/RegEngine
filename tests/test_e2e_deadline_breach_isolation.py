"""Isolation guard for the deadline breach E2E suite.

The deadline tests in tests/test_e2e_deadline_breach.py once handed a case
id through a class attribute set by an earlier test, so every later test
failed when run on its own. These checks parse that file and prove each
test now gets its case from a fixture instead of shared mutable state.
They need no database.
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).with_name("test_e2e_deadline_breach.py")

# Tests that need a case to do anything useful. test_00 only ingests
# events, so it is exempt from the fixture requirement.
CASE_TESTS = (
    "test_01_create_case_with_1h_deadline",
    "test_02_deadline_1h_is_urgent",
    "test_03_simulate_deadline_breach",
    "test_04_breached_deadline_is_overdue",
    "test_05_overdue_case_still_functional_scope",
    "test_06_overdue_case_still_functional_collect",
    "test_07_overdue_case_still_functional_package",
    "test_08_boundary_2h_is_critical",
    "test_09_boundary_exactly_2h_is_urgent",
    "test_10_boundary_6h_is_normal",
    "test_11_boundary_just_under_6h_is_urgent",
)


def _parse():
    return ast.parse(SOURCE.read_text())


def _fixture_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                dec_name = ""
                if isinstance(dec, ast.Name):
                    dec_name = dec.id
                elif isinstance(dec, ast.Attribute):
                    dec_name = dec.attr
                elif isinstance(dec, ast.Call):
                    func = dec.func
                    if isinstance(func, ast.Name):
                        dec_name = func.id
                    elif isinstance(func, ast.Attribute):
                        dec_name = func.attr
                if dec_name == "fixture":
                    names.add(node.name)
    return names


def _class_test_args(tree):
    args_by_name = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "TestDeadlineBreachE2E":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                    args_by_name[item.name] = {a.arg for a in item.args.args}
    return args_by_name


def test_case_fixture_creates_case():
    """A case_id fixture exists and creates the case itself."""
    tree = _parse()
    assert "case_id" in _fixture_names(tree), "missing case_id fixture"
    text = SOURCE.read_text()
    fixture_body = text.split("def case_id", 1)[1].split("\n@pytest", 1)[0]
    assert "create_request_case" in fixture_body or "_create_deadline_case" in fixture_body, (
        "case_id fixture must create the case"
    )


def test_no_class_attribute_state_sharing():
    """No test passes state through a _case_id class attribute."""
    tree = _parse()
    shared = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "_case_id"]
    assert shared == [], "tests still share state via a _case_id attribute"


def test_later_tests_take_case_fixture():
    """Every case-dependent test declares the case_id fixture."""
    missing = [
        name for name, args in _class_test_args(_parse()).items() if name in CASE_TESTS and "case_id" not in args
    ]
    assert missing == [], f"tests missing case_id fixture: {missing}"
