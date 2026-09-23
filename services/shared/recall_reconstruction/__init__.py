"""Recall-scope reconstruction from pallet-level source records.

DB-free engine that links lot -> pallet contents -> shipment -> receipt ->
subsequent movement, reports every gap it cannot close, and labels each
worksheet row with exactly one of three verdicts (see :mod:`labels`).

Missing evidence is never read as exclusion: a row is ``unresolved`` until a
record closes the gap, and the practitioner decides scope, not the engine.
"""

from .chain import build_custody
from .labels import FindingType, LinkLabel
from .loader import CASES, load_fixture
from .package import build_package, run_case
from .worksheet import build_worksheet

__all__ = [
    "CASES",
    "FindingType",
    "LinkLabel",
    "build_custody",
    "build_package",
    "build_worksheet",
    "load_fixture",
    "run_case",
]
