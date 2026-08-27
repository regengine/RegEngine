"""Regression coverage for the packaged Python SDK."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import regengine
from regengine import RegEngineClient


def _setup_kwargs() -> dict[str, ast.AST]:
    setup_path = Path(__file__).resolve().parents[2] / "regengine" / "setup.py"
    module = ast.parse(setup_path.read_text(encoding="utf-8"))
    setup_call = next(
        node for node in ast.walk(module) if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup"
    )
    return {kw.arg: kw.value for kw in setup_call.keywords}


def test_sdk_import_and_client_constructor() -> None:
    client = RegEngineClient(api_key="rge_test")
    try:
        assert client.api_key == "rge_test"  # pragma: allowlist secret
    finally:
        client._session.close()


def test_setup_declares_runtime_http_clients() -> None:
    install_requires = ast.literal_eval(_setup_kwargs()["install_requires"])
    assert any(requirement.startswith("httpx>=") for requirement in install_requires)
    assert any(requirement.startswith("requests>=") for requirement in install_requires)


def test_version_single_source_of_truth() -> None:
    """WS-11: __init__.py is the only place the version string lives.

    setup.py must NOT carry its own literal — it reads __version__ from
    __init__.py at build time (the pre-WS-11 state had three diverging
    strings: setup.py 0.1.0.dev0, CHANGELOG 1.1.0, verify_chain 1.0.0).
    """
    version_kwarg = _setup_kwargs()["version"]
    # A literal string here means someone reintroduced a second copy.
    assert not isinstance(version_kwarg, ast.Constant), (
        "setup.py hardcodes version= again — it must derive from "
        "regengine/__init__.py __version__ (WS-11 single source of truth)"
    )
    setup_text = (Path(__file__).resolve().parents[2] / "regengine" / "setup.py").read_text(encoding="utf-8")
    assert "__version__" in setup_text
    assert regengine.__version__.count(".") >= 2


def test_verifier_version_derives_from_package() -> None:
    """regengine-verify --version must report the package version, not a
    hardcoded string (pre-WS-11 it claimed 1.0.0 while the package was
    0.1.0.dev0)."""
    from regengine import verify_records

    assert verify_records._sdk_version() == regengine.__version__


def _python_floor() -> tuple[int, int]:
    """The minimum Python version setup.py's python_requires advertises."""
    python_requires = ast.literal_eval(_setup_kwargs()["python_requires"])
    match = re.search(r">=\s*(\d+)\.(\d+)", python_requires)
    assert match, f"cannot parse a floor out of python_requires={python_requires!r}"
    return int(match.group(1)), int(match.group(2))


def _classifier_versions() -> list[tuple[int, int]]:
    classifiers = ast.literal_eval(_setup_kwargs()["classifiers"])
    versions = []
    for classifier in classifiers:
        match = re.fullmatch(r"Programming Language :: Python :: (\d+)\.(\d+)", classifier)
        if match:
            versions.append((int(match.group(1)), int(match.group(2))))
    return versions


def _minimum_python_for_source(path: Path) -> tuple[int, int]:
    """Lowest Python on which importing ``path`` can succeed.

    PEP 585 builtin generics (``list[X]``) in annotations that are *evaluated*
    — i.e. no ``from __future__ import annotations`` — raise
    ``TypeError: 'type' object is not subscriptable`` below 3.9.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    has_future_annotations = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in ast.walk(tree)
    )
    if has_future_annotations:
        return (3, 8)

    builtin_generics = {"list", "dict", "tuple", "set", "frozenset", "type"}
    annotations: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                annotations.append(node.returns)
            annotations.extend(a.annotation for a in node.args.args if a.annotation is not None)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            annotations.append(node.annotation)

    for annotation in annotations:
        for sub in ast.walk(annotation):
            if isinstance(sub, ast.Subscript) and getattr(sub.value, "id", None) in builtin_generics:
                return (3, 9)
    return (3, 8)


def test_python_requires_matches_the_console_script_module() -> None:
    """#2954: python_requires must not advertise a Python on which the module
    behind the only console script cannot even be imported.

    ``regengine-verify=regengine.verify_records:main`` is that module; it used
    to carry evaluated ``list[VerificationResult]`` annotations with no
    ``from __future__ import annotations`` while setup.py claimed ``>=3.8``.
    """
    verifier = Path(__file__).resolve().parents[2] / "regengine" / "verify_records.py"
    required = _minimum_python_for_source(verifier)
    floor = _python_floor()
    assert floor >= required, (
        f"setup.py declares python_requires floor {floor[0]}.{floor[1]}, but "
        f"{verifier.name} cannot be imported below {required[0]}.{required[1]}"
    )


def test_classifiers_do_not_advertise_versions_below_the_floor() -> None:
    floor = _python_floor()
    below = [v for v in _classifier_versions() if v < floor]
    assert not below, "classifiers advertise Python versions below python_requires: " + ", ".join(
        f"{major}.{minor}" for major, minor in below
    )


def test_deprecation_shim_still_imports() -> None:
    """The verify_chain shim re-exports from verify_records, so it breaks
    wherever that module breaks (#2954)."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import regengine.verify_chain as shim

    assert callable(shim.main)
