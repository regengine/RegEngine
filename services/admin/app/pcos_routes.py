"""
Production Compliance OS — API Routes (SHIM)

This file previously contained the monolithic PCOS routes.
All endpoints have been extracted to the app/pcos/ package:

    - app/pcos/dashboard.py   — Dashboard metrics
    - app/pcos/entities.py    — Companies, Projects, Locations, People, Engagements, Tasks
    - app/pcos/gate.py        — Gate status & greenlight workflow
    - app/pcos/evidence.py    — Evidence, document uploads, risks, guidance
    - app/pcos/budget.py      — Budgets, rate validation, tax credits, fringes
    - app/pcos/compliance.py  — Forms, worker classification, paperwork, snapshots, audit
    - app/pcos/governance.py  — Schema version, analysis runs, corrections
    - app/pcos/authority.py   — Authority documents, facts, verdicts, lineage

This file is kept as a backward-compatible shim so that existing imports
(e.g. `from app.pcos_routes import router`) continue to work.
The actual router object is re-exported from app.pcos.__init__.

See docs/PCOS_DECOMPOSITION_PLAN.md for the full extraction roadmap.
"""

from __future__ import annotations

# Re-export the unified router from the pcos package
from .pcos import router  # noqa: F401

__all__ = ["router"]
