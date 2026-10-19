"""Jev Lab: a local sandbox and a Claude <-> Jev self-improving loop. Experimental dev tooling.

Run it from the repo root on your own machine:

    venv/bin/python scripts/jev_lab serve            # live Jev, needs TYPESAFE_API_KEY
    venv/bin/python scripts/jev_lab serve --fake     # offline fake Jev, nothing leaves the machine
    venv/bin/python scripts/jev_lab loop --fake --proposer offline --generations 3

What it does:

* **Sandbox.** A local web page (127.0.0.1 only, per-run token) where you ask
  Jev typed questions (choice, yes/no, score) or paste a CSV header row and see
  the two answers ``POST /api/v1/ingest/csv`` would get, with confidence.
* **Loop.** Jev answers RegEngine's labelled header rows
  (``docs/engineering/examples/jev_eval_cases.json`` plus the seven templates
  and any rows you label in the sandbox). Claude reads only the *training*
  split's misses and uncertain answers and rewrites the question wording and
  option descriptions. A rewrite becomes the new incumbent only when it beats
  the incumbent on the *held-out* split (confidence Brier score by a margin,
  no lost correct answers, no new wrong answer at the auto-apply threshold).
  Every generation is recorded in a local ledger.
* **Constellation.** The page draws every labelled header as a star: its
  brightness is Jev's confidence, its colour whether Jev was right, hollow
  stars are held out from Claude, and each generation is an orbit ring.

What it never does: edit production code or the production question sets,
send row values, tenant data or secrets to Jev or Claude, or print the API key.
Promotion of a better question set is a PR that a person reviews.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def ensure_import_paths() -> None:
    """Make ``shared`` and the ingestion ``app`` package importable, as ``scripts/jev_eval.py`` does.

    ``scripts/`` itself is never put on ``sys.path``: its directories
    (``security``, ``scheduler``, ...) would shadow packages of the same name.
    """
    for path in (ROOT / "services" / "ingestion", ROOT / "services"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def load_script(name: str) -> ModuleType:
    """``scripts/<name>.py`` as module ``name``, loaded once (the way its own tests load it)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


ensure_import_paths()
