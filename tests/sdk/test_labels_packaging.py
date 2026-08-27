"""#2957: regengine/labels.py ships in the distribution, so it must import
without undeclared third-party packages, and its PDF path must never hand back
PNG bytes.

``setup.py`` uses ``packages=["regengine"], package_dir={"regengine": "."}``
with no ``MANIFEST.in`` and no exclude rule, so every ``.py`` file in the
directory — ``labels.py`` included — is copied into the built distribution.
Before the fix, ``labels.py`` did a module-level ``import qrcode`` while
``qrcode`` was declared in no manifest anywhere in the repository, so
``import regengine.labels`` raised ``ModuleNotFoundError`` in a clean install.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SDK_DIR = REPO_ROOT / "regengine"

# Import name -> distribution name, for the cases where they differ.
_IMPORT_TO_DISTRIBUTION = {
    "PIL": "pillow",
    "fpdf": "fpdf2",
    "yaml": "pyyaml",
}


def _normalize(name: str) -> str:
    """PEP 503 normalization of a distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_distributions() -> set[str]:
    """Every distribution name setup.py declares, required or extra."""
    module = ast.parse((SDK_DIR / "setup.py").read_text(encoding="utf-8"))
    setup_call = next(
        node for node in ast.walk(module) if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "setup"
    )
    kwargs = {kw.arg: kw.value for kw in setup_call.keywords}

    requirements: list[str] = list(ast.literal_eval(kwargs["install_requires"]))
    for extra_requirements in ast.literal_eval(kwargs["extras_require"]).values():
        requirements.extend(extra_requirements)

    # Strip version specifiers / markers: "Pillow>=10.0.0" -> "pillow".
    return {_normalize(re.split(r"[<>=!~;\[\s]", requirement, 1)[0]) for requirement in requirements}


def _module_level_third_party_imports(path: Path) -> set[str]:
    """Top-level (module-scope) imports that are not stdlib and not relative."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:  # module scope only — function-local imports are lazy
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import, in-package
                continue
            if node.module:
                found.add(node.module.split(".")[0])
    stdlib = getattr(sys, "stdlib_module_names", frozenset())
    return {name for name in found if name not in stdlib and name != "regengine"}


def test_labels_module_imports_without_the_labels_extra_installed():
    """Importing the module must never require an optional package.

    `qrcode` is deliberately absent from this environment; before the fix this
    import raised ModuleNotFoundError.
    """
    assert importlib.util.find_spec("qrcode") is None, (
        "this test is only meaningful while qrcode is absent; if it is now a "
        "declared runtime dependency, update this assertion deliberately"
    )
    module = importlib.import_module("regengine.labels")
    assert module.LabelData is not None


@pytest.mark.parametrize(
    "module_path",
    sorted(p.name for p in SDK_DIR.glob("*.py") if p.name != "setup.py"),
)
def test_every_shipped_module_imports(module_path):
    """Acceptance criterion: every module in the built distribution imports.

    ``package_dir={"regengine": "."}`` sweeps all of these into the wheel, so
    an undeclared dependency in any of them is a broken customer artifact.
    """
    name = module_path[: -len(".py")]
    if name == "__init__":
        name = ""
    target = f"regengine.{name}" if name else "regengine"
    importlib.import_module(target)


def test_third_party_imports_in_labels_are_declared_dependencies():
    """Automated check for acceptance criterion 3: no module-level import in
    labels.py may reference a package setup.py never declares."""
    declared = _declared_distributions()
    undeclared = {
        name
        for name in _module_level_third_party_imports(SDK_DIR / "labels.py")
        if _normalize(_IMPORT_TO_DISTRIBUTION.get(name, name)) not in declared
    }
    assert not undeclared, (
        f"regengine/labels.py imports {sorted(undeclared)} at module level, but "
        f"setup.py declares none of them. Declared: {sorted(declared)}"
    )


def test_labels_extra_declares_qrcode_pillow_and_fpdf():
    declared = _declared_distributions()
    assert {"qrcode", "pillow", "fpdf2"} <= declared


class TestPdfNeverReturnsPng:
    def test_png_fallback_is_gone(self):
        from regengine import labels

        assert not hasattr(labels, "_png_to_simple_pdf"), (
            "_png_to_simple_pdf returned the PNG bytes unchanged, which "
            "generate_batch_labels then wrote under a .pdf filename"
        )

    def test_generate_label_pdf_raises_when_fpdf_missing(self, monkeypatch):
        """No silent format substitution: without fpdf2 the call fails."""
        from regengine import labels

        # Blocking the module makes `from fpdf import FPDF` raise ImportError.
        monkeypatch.setitem(sys.modules, "fpdf", None)
        label = labels.LabelData(
            traceability_lot_code="LOT-A",
            product_description="Romaine",
            quantity=10,
            unit_of_measure="cases",
            location_gln="0614141000001",
            location_name="Salinas, CA",
            lot_date="2026-02-06",
        )

        with pytest.raises(ImportError) as excinfo:
            labels.generate_label_pdf(label)

        message = str(excinfo.value)
        assert "fpdf2" in message
        assert "regengine[labels]" in message


def test_missing_optional_import_names_the_extra():
    """The error a user hits must say how to fix it."""
    from regengine import labels

    with pytest.raises(ImportError) as excinfo:
        labels.generate_qr("LOT-A")
    assert "regengine[labels]" in str(excinfo.value)
