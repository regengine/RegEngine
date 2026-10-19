"""``python scripts/jev_lab ...``: run Jev Lab's command line."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# Running the directory puts it first on sys.path; its module names must not
# shadow anything, and scripts/ must not be put there either. Load the
# package by path instead.
if sys.path and Path(sys.path[0] or ".").resolve() == _HERE:
    sys.path.pop(0)
if "jev_lab" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "jev_lab", _HERE / "__init__.py", submodule_search_locations=[str(_HERE)]
    )
    assert _spec is not None and _spec.loader is not None
    _package = importlib.util.module_from_spec(_spec)
    sys.modules["jev_lab"] = _package
    _spec.loader.exec_module(_package)

from jev_lab.cli import configure_logging, main  # noqa: E402

if __name__ == "__main__":
    configure_logging()
    sys.exit(main())
