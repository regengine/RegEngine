#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  PR #401 Audit Script — Trace-Back / Recall Readiness                  ║
║                                                                        ║
║  Run:  PYTHONPATH=services/ingestion:services:. python3                 ║
║        tests/audit/audit_trace_back.py                                 ║
║                                                                        ║
║  Audits the in-memory BFS trace engine + /api/v1/sandbox/trace         ║
║  endpoint + frontend component structure. Produces a graded report.    ║
╚══════════════════════════════════════════════════════════════════════════╝

Sections:
  A. Engine Correctness    (40 pts)  — BFS traversal, link following, edge cases
  B. API Contract          (20 pts)  — Pydantic models, endpoint validation, error handling
  C. Frontend Wiring       (15 pts)  — Component structure, type safety, integration
  D. Security & Guardrails (10 pts)  — Rate limiting, input caps, no data persistence
  E. Code Quality          (15 pts)  — Naming, docstrings, test coverage, no dead code

Total: 100 pts
  90-100 = SHIP IT
  75-89  = MINOR ISSUES — fix before merge
  60-74  = NEEDS WORK — significant gaps
  < 60   = REJECT — rethink approach
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import subprocess
import sys
import textwrap
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_FILE = REPO_ROOT / "services" / "ingestion" / "app" / "sandbox_router.py"
TRACE_PANEL = REPO_ROOT / "frontend" / "src" / "components" / "marketing" / "sandbox-grid" / "TracePanel.tsx"
GRID_COMPONENT = REPO_ROOT / "frontend" / "src" / "components" / "marketing" / "sandbox-grid" / "SandboxGrid.tsx"
GRID_TOOLBAR = REPO_ROOT / "frontend" / "src" / "components" / "marketing" / "sandbox-grid" / "GridToolbar.tsx"
BARREL_INDEX = REPO_ROOT / "frontend" / "src" / "components" / "marketing" / "sandbox-grid" / "index.ts"
TEST_FILE = REPO_ROOT / "tests" / "test_trace_engine.py"


@dataclass
class Check:
    name: str
    section: str
    max_points: float
    earned: float = 0.0
    passed: bool = False
    detail: str = ""


@dataclass
class AuditReport:
    checks: List[Check] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    def add(self, check: Check):
        self.checks.append(check)

    @property
    def total_earned(self) -> float:
        return sum(c.earned for c in self.checks)

    @property
    def total_possible(self) -> float:
        return sum(c.max_points for c in self.checks)

    def section_score(self, section: str) -> Tuple[float, float]:
        earned = sum(c.earned for c in self.checks if c.section == section)
        possible = sum(c.max_points for c in self.checks if c.section == section)
        return earned, possible


# ---------------------------------------------------------------------------
# CSV Test Fixtures
# ---------------------------------------------------------------------------

# 9-event multi-lot: LOT-A + LOT-B → transformation → LOT-MEGA → retail
MULTI_LOT_CSV = textwrap.dedent("""\
    cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,input_traceability_lot_codes
    harvesting,LOT-A,Romaine Lettuce,1000,lbs,Farm Alpha,2026-03-10T08:00:00Z,
    shipping,LOT-A,Romaine Lettuce,1000,lbs,Farm Alpha DC,2026-03-11T06:00:00Z,
    receiving,LOT-A,Romaine Lettuce,1000,lbs,Processing Plant,2026-03-11T14:00:00Z,
    harvesting,LOT-B,Iceberg Lettuce,500,lbs,Farm Beta,2026-03-10T09:00:00Z,
    shipping,LOT-B,Iceberg Lettuce,500,lbs,Farm Beta DC,2026-03-11T07:00:00Z,
    receiving,LOT-B,Iceberg Lettuce,500,lbs,Processing Plant,2026-03-11T15:00:00Z,
    transformation,LOT-MEGA,Mixed Salad,1400,lbs,Processing Plant,2026-03-12T10:00:00Z,"LOT-A,LOT-B"
    shipping,LOT-MEGA,Mixed Salad,1400,lbs,Processing Plant,2026-03-13T06:00:00Z,
    receiving,LOT-MEGA,Mixed Salad,1400,lbs,Retailer,2026-03-13T14:00:00Z,
""")

# 3-event simple chain — no transformations
SIMPLE_CSV = textwrap.dedent("""\
    cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp
    harvesting,LOT-001,Romaine Lettuce,2000,lbs,Valley Fresh Farms,2026-03-12T08:00:00Z
    shipping,LOT-001,Romaine Lettuce,2000,lbs,Valley Fresh DC,2026-03-13T06:00:00Z
    receiving,LOT-001,Romaine Lettuce,1900,lbs,FreshCo Distribution,2026-03-13T14:00:00Z
""")

# Diamond pattern: two raw lots → two separate transformations → shared downstream lot
DIAMOND_CSV = textwrap.dedent("""\
    cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,input_traceability_lot_codes
    harvesting,RAW-1,Spinach,800,lbs,Farm X,2026-03-01T08:00:00Z,
    harvesting,RAW-2,Kale,600,lbs,Farm Y,2026-03-01T09:00:00Z,
    transformation,MIX-1,Greens Mix,700,lbs,Plant A,2026-03-02T10:00:00Z,RAW-1
    transformation,MIX-2,Kale Blend,500,lbs,Plant B,2026-03-02T11:00:00Z,RAW-2
    transformation,FINAL,Superfood Salad,1100,lbs,Plant C,2026-03-03T12:00:00Z,"MIX-1,MIX-2"
    shipping,FINAL,Superfood Salad,1100,lbs,Plant C,2026-03-04T06:00:00Z,
""")

# Edge case: orphaned lot with no links
ORPHAN_CSV = textwrap.dedent("""\
    cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,input_traceability_lot_codes
    harvesting,LOT-LINKED,Product A,500,lbs,Farm,2026-03-01T08:00:00Z,
    shipping,LOT-LINKED,Product A,500,lbs,Farm DC,2026-03-02T06:00:00Z,
    harvesting,LOT-ORPHAN,Product B,300,lbs,Other Farm,2026-03-01T08:00:00Z,
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def file_exists(path: Path) -> bool:
    return path.exists() and path.is_file()


def file_contains(path: Path, pattern: str, regex: bool = False) -> bool:
    """Check if file contains string or regex pattern."""
    if not file_exists(path):
        return False
    content = path.read_text()
    if regex:
        return bool(re.search(pattern, content))
    return pattern in content


def count_pattern(path: Path, pattern: str) -> int:
    """Count regex occurrences in a file."""
    if not file_exists(path):
        return 0
    return len(re.findall(pattern, path.read_text()))


def run_pytest(test_path: str, timeout: int = 60) -> Tuple[int, int, str]:
    """Run pytest and return (passed, failed, output)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short", "-q"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": "services/ingestion:services:."},
        )
        output = result.stdout + result.stderr
        # Parse "X passed, Y failed"
        match = re.search(r"(\d+) passed", output)
        passed = int(match.group(1)) if match else 0
        match = re.search(r"(\d+) failed", output)
        failed = int(match.group(1)) if match else 0
        return passed, failed, output
    except subprocess.TimeoutExpired:
        return 0, 0, "TIMEOUT"
    except Exception as e:
        return 0, 0, str(e)


def run_tsc(timeout: int = 120) -> Tuple[bool, str]:
    """Run TypeScript compiler check and return (success, output)."""
    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(REPO_ROOT / "frontend"),
        )
        output = result.stdout + result.stderr
        # Filter out pre-existing e2e errors
        lines = [l for l in output.splitlines()
                 if l.strip() and "e2e/" not in l and "security-audit" not in l]
        clean = len(lines) == 0
        return clean, "\n".join(lines) if lines else "Clean"
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════
# Section A: Engine Correctness (40 pts)
# ═══════════════════════════════════════════════════════════════════════════

def audit_engine_correctness(report: AuditReport):
    """Test the BFS trace engine with increasingly complex scenarios."""
    section = "A. Engine Correctness"

    # Import the trace engine
    try:
        from app.sandbox_router import _trace_in_memory, _parse_csv_to_events
        imported = True
    except Exception as e:
        imported = False
        report.add(Check(
            name="Import trace engine",
            section=section, max_points=40, earned=0,
            detail=f"FATAL: Cannot import — {e}",
        ))
        return

    # --- A1: Downstream from LOT-A reaches LOT-MEGA (5 pts) ---
    events = _parse_csv_to_events(MULTI_LOT_CSV)
    r = _trace_in_memory(events, "LOT-A", "downstream")
    lots = set(r.lots_touched)
    ok = "LOT-A" in lots and "LOT-MEGA" in lots and "LOT-B" not in lots
    report.add(Check(
        name="A1: Downstream LOT-A → LOT-MEGA only (not LOT-B)",
        section=section, max_points=5, earned=5 if ok else 0, passed=ok,
        detail=f"lots_touched={r.lots_touched}" if not ok else "OK",
    ))

    # --- A2: Upstream from LOT-MEGA reaches both inputs (5 pts) ---
    r2 = _trace_in_memory(events, "LOT-MEGA", "upstream")
    lots2 = set(r2.lots_touched)
    ok2 = lots2 == {"LOT-A", "LOT-B", "LOT-MEGA"}
    report.add(Check(
        name="A2: Upstream LOT-MEGA → {LOT-A, LOT-B, LOT-MEGA}",
        section=section, max_points=5, earned=5 if ok2 else 0, passed=ok2,
        detail=f"lots_touched={r2.lots_touched}" if not ok2 else "OK",
    ))

    # --- A3: Bidirectional reaches entire graph (5 pts) ---
    r3 = _trace_in_memory(events, "LOT-A", "both")
    ok3 = len(r3.nodes) == 9 and len(r3.lots_touched) == 3
    report.add(Check(
        name="A3: Bidirectional LOT-A → all 9 events, 3 lots",
        section=section, max_points=5, earned=5 if ok3 else 0, passed=ok3,
        detail=f"nodes={len(r3.nodes)}, lots={len(r3.lots_touched)}" if not ok3 else "OK",
    ))

    # --- A4: Edges are generated between nodes (3 pts) ---
    ok4 = len(r3.edges) > 0
    link_types = {e.link_type for e in r3.edges}
    has_both = "same_lot" in link_types and any("transformation" in lt for lt in link_types)
    earned4 = 3 if (ok4 and has_both) else (1.5 if ok4 else 0)
    report.add(Check(
        name="A4: Edge generation with correct link_types",
        section=section, max_points=3, earned=earned4, passed=ok4 and has_both,
        detail=f"edges={len(r3.edges)}, link_types={link_types}",
    ))

    # --- A5: Simple chain (no transformations) (3 pts) ---
    simple_events = _parse_csv_to_events(SIMPLE_CSV)
    r5 = _trace_in_memory(simple_events, "LOT-001", "both")
    ok5 = len(r5.nodes) == 3 and r5.lots_touched == ["LOT-001"]
    report.add(Check(
        name="A5: Simple 3-event chain — no transformation needed",
        section=section, max_points=3, earned=3 if ok5 else 0, passed=ok5,
        detail=f"nodes={len(r5.nodes)}, lots={r5.lots_touched}" if not ok5 else "OK",
    ))

    # --- A6: Diamond graph (two paths to FINAL) (5 pts) ---
    diamond_events = _parse_csv_to_events(DIAMOND_CSV)
    r6 = _trace_in_memory(diamond_events, "FINAL", "upstream")
    lots6 = set(r6.lots_touched)
    expected = {"RAW-1", "RAW-2", "MIX-1", "MIX-2", "FINAL"}
    ok6 = lots6 == expected
    report.add(Check(
        name="A6: Diamond upstream — FINAL traces back to RAW-1,RAW-2 via MIX-1,MIX-2",
        section=section, max_points=5, earned=5 if ok6 else 0, passed=ok6,
        detail=f"expected={expected}, got={lots6}" if not ok6 else "OK",
    ))

    # --- A7: Downstream from RAW-1 reaches FINAL (3 pts) ---
    r7 = _trace_in_memory(diamond_events, "RAW-1", "downstream")
    lots7 = set(r7.lots_touched)
    ok7 = "FINAL" in lots7 and "MIX-1" in lots7
    report.add(Check(
        name="A7: Diamond downstream RAW-1 → MIX-1 → FINAL",
        section=section, max_points=3, earned=3 if ok7 else 0, passed=ok7,
        detail=f"lots_touched={r7.lots_touched}" if not ok7 else "OK",
    ))

    # --- A8: Orphan lot isolation (3 pts) ---
    orphan_events = _parse_csv_to_events(ORPHAN_CSV)
    r8 = _trace_in_memory(orphan_events, "LOT-LINKED", "both")
    ok8 = "LOT-ORPHAN" not in set(r8.lots_touched)
    report.add(Check(
        name="A8: Orphan lot not contaminating linked-lot trace",
        section=section, max_points=3, earned=3 if ok8 else 0, passed=ok8,
        detail=f"lots_touched={r8.lots_touched}" if not ok8 else "OK",
    ))

    # --- A9: Missing TLC returns empty (2 pts) ---
    r9 = _trace_in_memory(events, "NONEXISTENT-TLC", "both")
    ok9 = len(r9.nodes) == 0 and r9.max_depth == 0
    report.add(Check(
        name="A9: Missing TLC → empty result (no crash)",
        section=section, max_points=2, earned=2 if ok9 else 0, passed=ok9,
        detail=f"nodes={len(r9.nodes)}" if not ok9 else "OK",
    ))

    # --- A10: max_depth=0 limits to seed lot only (3 pts) ---
    r10 = _trace_in_memory(events, "LOT-A", "downstream", max_depth=0)
    all_seed = all(n.traceability_lot_code == "LOT-A" for n in r10.nodes)
    ok10 = all_seed and len(r10.nodes) == 3
    report.add(Check(
        name="A10: max_depth=0 → only seed lot events",
        section=section, max_points=3, earned=3 if ok10 else 0, passed=ok10,
        detail=f"nodes={len(r10.nodes)}, all_seed={all_seed}" if not ok10 else "OK",
    ))

    # --- A11: No duplicate nodes (infinite loop check) (3 pts) ---
    event_indices = [n.event_index for n in r3.nodes]
    ok11 = len(event_indices) == len(set(event_indices))
    report.add(Check(
        name="A11: No duplicate nodes in BFS (visited set works)",
        section=section, max_points=3, earned=3 if ok11 else 0, passed=ok11,
        detail=f"total={len(event_indices)}, unique={len(set(event_indices))}" if not ok11 else "OK",
    ))


# ═══════════════════════════════════════════════════════════════════════════
# Section B: API Contract (20 pts)
# ═══════════════════════════════════════════════════════════════════════════

def audit_api_contract(report: AuditReport):
    """Verify Pydantic models, endpoint structure, and validation."""
    section = "B. API Contract"

    # --- B1: Pydantic models exist (4 pts) ---
    try:
        from app.sandbox_router import (
            TraceNode, TraceEdge, TraceGraphResponse, SandboxTraceRequest,
        )
        ok = True
        detail = "OK"
    except ImportError as e:
        ok = False
        detail = str(e)
    report.add(Check(
        name="B1: Pydantic models — TraceNode, TraceEdge, TraceGraphResponse, SandboxTraceRequest",
        section=section, max_points=4, earned=4 if ok else 0, passed=ok, detail=detail,
    ))

    if not ok:
        # Can't continue without models
        for name, pts in [("B2", 4), ("B3", 4), ("B4", 4), ("B5", 4)]:
            report.add(Check(name=f"{name}: SKIPPED", section=section, max_points=pts, detail="Models not importable"))
        return

    # --- B2: TraceNode has required fields (4 pts) ---
    node_fields = set(TraceNode.model_fields.keys())
    required = {"event_index", "cte_type", "traceability_lot_code", "product_description", "depth"}
    ok2 = required.issubset(node_fields)
    report.add(Check(
        name="B2: TraceNode has core fields (event_index, cte_type, tlc, product, depth)",
        section=section, max_points=4, earned=4 if ok2 else 0, passed=ok2,
        detail=f"missing={required - node_fields}" if not ok2 else f"fields={len(node_fields)}",
    ))

    # --- B3: TraceGraphResponse shape (4 pts) ---
    resp_fields = set(TraceGraphResponse.model_fields.keys())
    required3 = {"seed_tlc", "direction", "nodes", "edges", "lots_touched", "facilities", "max_depth"}
    ok3 = required3.issubset(resp_fields)
    report.add(Check(
        name="B3: TraceGraphResponse has required response fields",
        section=section, max_points=4, earned=4 if ok3 else 0, passed=ok3,
        detail=f"missing={required3 - resp_fields}" if not ok3 else f"fields={len(resp_fields)}",
    ))

    # --- B4: Endpoint route registered on sandbox router (4 pts) ---
    backend_src = BACKEND_FILE.read_text()
    has_route = '@router.post(' in backend_src and '"/trace"' in backend_src
    has_response_model = 'response_model=TraceGraphResponse' in backend_src
    ok4 = has_route and has_response_model
    report.add(Check(
        name="B4: POST /trace endpoint registered with response_model",
        section=section, max_points=4, earned=4 if ok4 else 0, passed=ok4,
        detail="route" + ("✓" if has_route else "✗") + " response_model" + ("✓" if has_response_model else "✗"),
    ))

    # --- B5: Endpoint validates inputs — empty CSV, empty TLC, >50 events (4 pts) ---
    validations = 0
    if 'CSV text is required' in backend_src:
        validations += 1
    if 'TLC (traceability lot code) is required' in backend_src or 'tlc' in backend_src.lower():
        validations += 1
    if 'Maximum 50 events' in backend_src:
        validations += 1
    if '_check_sandbox_rate_limit' in backend_src:
        # Check it's called in the trace endpoint
        trace_fn_start = backend_src.find("async def sandbox_trace")
        if trace_fn_start > -1:
            trace_fn_body = backend_src[trace_fn_start:trace_fn_start + 800]
            if "_check_sandbox_rate_limit" in trace_fn_body:
                validations += 1
    ok5 = validations >= 3
    report.add(Check(
        name="B5: Input validation (empty CSV, empty TLC, 50-event cap, rate limit)",
        section=section, max_points=4, earned=min(4, validations), passed=ok5,
        detail=f"{validations}/4 validations present",
    ))


# ═══════════════════════════════════════════════════════════════════════════
# Section C: Frontend Wiring (15 pts)
# ═══════════════════════════════════════════════════════════════════════════

def audit_frontend_wiring(report: AuditReport):
    """Verify frontend component structure and integration."""
    section = "C. Frontend Wiring"

    # --- C1: TracePanel.tsx exists with core elements (4 pts) ---
    ok1 = file_exists(TRACE_PANEL)
    checks1 = 0
    if ok1:
        content = TRACE_PANEL.read_text()
        if "TracePanel" in content:
            checks1 += 1
        if "/api/ingestion/api/v1/sandbox/trace" in content:
            checks1 += 1
        if "direction" in content:
            checks1 += 1
        if "export" in content.lower() or "Export" in content:
            checks1 += 1
    earned1 = checks1
    report.add(Check(
        name="C1: TracePanel.tsx — component, API call, direction control, export",
        section=section, max_points=4, earned=earned1, passed=checks1 >= 3,
        detail=f"{checks1}/4 elements found" if ok1 else "FILE MISSING",
    ))

    # --- C2: TracePanel renders CTE nodes with visual differentiation (3 pts) ---
    checks2 = 0
    if ok1:
        content = TRACE_PANEL.read_text()
        cte_types = ["harvesting", "shipping", "receiving", "transformation"]
        found = sum(1 for c in cte_types if c in content)
        if found >= 3:
            checks2 += 1
        if "getCteVisual" in content or "CTE_COLORS" in content:
            checks2 += 1
        if "lotGroups" in content or "lot_code" in content.lower():
            checks2 += 1
    report.add(Check(
        name="C2: CTE event nodes with color differentiation + lot grouping",
        section=section, max_points=3, earned=checks2, passed=checks2 >= 2,
        detail=f"{checks2}/3 visual elements found",
    ))

    # --- C3: SandboxGrid imports and renders TracePanel (3 pts) ---
    grid_ok = file_exists(GRID_COMPONENT)
    checks3 = 0
    if grid_ok:
        content = GRID_COMPONENT.read_text()
        if "TracePanel" in content:
            checks3 += 1
        if "showTrace" in content:
            checks3 += 1
        if "availableTlcs" in content:
            checks3 += 1
    report.add(Check(
        name="C3: SandboxGrid imports TracePanel, has showTrace toggle + availableTlcs",
        section=section, max_points=3, earned=checks3, passed=checks3 >= 2,
        detail=f"{checks3}/3 integration points found",
    ))

    # --- C4: GridToolbar has Trace toggle button (2 pts) ---
    toolbar_ok = file_exists(GRID_TOOLBAR)
    checks4 = 0
    if toolbar_ok:
        content = GRID_TOOLBAR.read_text()
        if "onToggleTrace" in content:
            checks4 += 1
        if "GitBranch" in content or "Trace" in content:
            checks4 += 1
    report.add(Check(
        name="C4: GridToolbar has Trace toggle with icon",
        section=section, max_points=2, earned=checks4, passed=checks4 >= 1,
        detail=f"{checks4}/2 toolbar elements found",
    ))

    # --- C5: Barrel export includes TracePanel (1 pt) ---
    ok5 = file_contains(BARREL_INDEX, "TracePanel")
    report.add(Check(
        name="C5: Barrel index.ts exports TracePanel",
        section=section, max_points=1, earned=1 if ok5 else 0, passed=ok5,
        detail="OK" if ok5 else "TracePanel not in index.ts",
    ))

    # --- C6: TypeScript compiles clean (2 pts) ---
    tsc_ok, tsc_output = run_tsc()
    report.add(Check(
        name="C6: TypeScript --noEmit passes (excluding pre-existing e2e errors)",
        section=section, max_points=2, earned=2 if tsc_ok else 0, passed=tsc_ok,
        detail="Clean" if tsc_ok else tsc_output[:200],
    ))


# ═══════════════════════════════════════════════════════════════════════════
# Section D: Security & Guardrails (10 pts)
# ═══════════════════════════════════════════════════════════════════════════

def audit_security(report: AuditReport):
    """Verify no data persistence, rate limiting, input capping."""
    section = "D. Security & Guardrails"
    backend_src = BACKEND_FILE.read_text()

    # --- D1: Rate limiting applied to trace endpoint (3 pts) ---
    trace_fn_start = backend_src.find("async def sandbox_trace")
    trace_body = backend_src[trace_fn_start:trace_fn_start + 1200] if trace_fn_start > -1 else ""
    ok1 = "_check_sandbox_rate_limit" in trace_body
    report.add(Check(
        name="D1: Rate limiting on /trace endpoint",
        section=section, max_points=3, earned=3 if ok1 else 0, passed=ok1,
        detail="OK" if ok1 else "_check_sandbox_rate_limit not called in sandbox_trace",
    ))

    # --- D2: 50-event cap enforced (2 pts) ---
    ok2 = "Maximum 50 events" in trace_body or "len(raw_events) > 50" in trace_body
    report.add(Check(
        name="D2: 50-event cap on trace endpoint",
        section=section, max_points=2, earned=2 if ok2 else 0, passed=ok2,
        detail="OK" if ok2 else "50-event check not found in trace endpoint body",
    ))

    # --- D3: max_depth capped at 20 (2 pts) ---
    ok3 = "min(max_depth, 20)" in backend_src
    report.add(Check(
        name="D3: max_depth capped at 20 to prevent runaway BFS",
        section=section, max_points=2, earned=2 if ok3 else 0, passed=ok3,
        detail="OK" if ok3 else "max_depth cap not found",
    ))

    # --- D4: No database session/ORM usage in trace engine (3 pts) ---
    trace_section = backend_src[backend_src.find("# Trace-Back / Recall"):]
    no_db = (
        "db.execute" not in trace_section
        and "Session" not in trace_section
        and "session" not in trace_section.lower().split("def _trace_in_memory")[0][-100:]
    )
    # More precise: check _trace_in_memory function signature
    fn_sig = re.search(r"def _trace_in_memory\([^)]+\)", backend_src)
    sig_no_db = fn_sig and "db" not in fn_sig.group(0) if fn_sig else False
    ok4 = no_db and sig_no_db
    report.add(Check(
        name="D4: No database/session usage in trace engine (stateless)",
        section=section, max_points=3, earned=3 if ok4 else 0, passed=ok4,
        detail="OK — pure in-memory BFS" if ok4 else "DB reference found in trace code",
    ))


# ═══════════════════════════════════════════════════════════════════════════
# Section E: Code Quality (15 pts)
# ═══════════════════════════════════════════════════════════════════════════

def audit_code_quality(report: AuditReport):
    """Naming, docstrings, test coverage, dead code."""
    section = "E. Code Quality"

    # --- E1: _trace_in_memory has docstring (2 pts) ---
    backend_src = BACKEND_FILE.read_text()
    fn_start = backend_src.find("def _trace_in_memory")
    if fn_start > -1:
        fn_body = backend_src[fn_start:fn_start + 500]
        ok1 = '"""' in fn_body or "'''" in fn_body
    else:
        ok1 = False
    report.add(Check(
        name="E1: _trace_in_memory has docstring",
        section=section, max_points=2, earned=2 if ok1 else 0, passed=ok1,
        detail="OK" if ok1 else "No docstring found",
    ))

    # --- E2: TracePanel.tsx has interface definitions (2 pts) ---
    tp_ok = file_exists(TRACE_PANEL)
    if tp_ok:
        tp_content = TRACE_PANEL.read_text()
        interfaces = len(re.findall(r"interface \w+", tp_content))
        ok2 = interfaces >= 3  # TraceNode, TraceEdge, TraceGraphResponse, TracePanelProps
    else:
        ok2 = False
        interfaces = 0
    report.add(Check(
        name="E2: TracePanel.tsx defines TypeScript interfaces",
        section=section, max_points=2, earned=2 if ok2 else 0, passed=ok2,
        detail=f"{interfaces} interfaces found" if tp_ok else "FILE MISSING",
    ))

    # --- E3: Existing test file with meaningful coverage (4 pts) ---
    passed_count, failed_count, test_output = run_pytest(
        "tests/test_trace_engine.py"
    )
    ok3 = passed_count >= 10 and failed_count == 0
    earned3 = 0
    if passed_count >= 14 and failed_count == 0:
        earned3 = 4
    elif passed_count >= 10 and failed_count == 0:
        earned3 = 3
    elif passed_count >= 5 and failed_count == 0:
        earned3 = 2
    elif passed_count > 0:
        earned3 = 1
    report.add(Check(
        name="E3: test_trace_engine.py — test count and pass rate",
        section=section, max_points=4, earned=earned3, passed=ok3,
        detail=f"{passed_count} passed, {failed_count} failed",
    ))

    # --- E4: No existing tests regressed (3 pts) ---
    passed_all, failed_all, all_output = run_pytest(
        "tests/test_rules_engine_unit.py"
    )
    ok4 = failed_all == 0 and passed_all >= 60
    report.add(Check(
        name="E4: Existing test_rules_engine_unit.py — no regressions",
        section=section, max_points=3, earned=3 if ok4 else 0, passed=ok4,
        detail=f"{passed_all} passed, {failed_all} failed",
    ))

    # --- E5: No console.log / print debug statements in new frontend code (2 pts) ---
    if tp_ok:
        tp_content = TRACE_PANEL.read_text()
        debug_prints = len(re.findall(r"console\.log\(", tp_content))
        ok5 = debug_prints == 0
    else:
        ok5 = False
        debug_prints = -1
    report.add(Check(
        name="E5: No console.log debug statements in TracePanel.tsx",
        section=section, max_points=2, earned=2 if ok5 else 0, passed=ok5,
        detail=f"{debug_prints} console.log found" if not ok5 else "OK",
    ))

    # --- E6: Consistent naming conventions (2 pts) ---
    checks6 = 0
    # Backend: snake_case for Python functions
    if re.search(r"def _trace_in_memory\(", backend_src):
        checks6 += 1
    # Frontend: PascalCase component, camelCase hooks
    if tp_ok:
        tp_content = TRACE_PANEL.read_text()
        if re.search(r"export function TracePanel", tp_content):
            checks6 += 1
    report.add(Check(
        name="E6: Naming conventions (snake_case backend, PascalCase frontend)",
        section=section, max_points=2, earned=checks6, passed=checks6 >= 2,
        detail=f"{checks6}/2 convention checks passed",
    ))


# ═══════════════════════════════════════════════════════════════════════════
# Report Rendering
# ═══════════════════════════════════════════════════════════════════════════

def render_report(report: AuditReport):
    elapsed = report.end_time - report.start_time
    total = report.total_earned
    possible = report.total_possible

    print()
    print("=" * 74)
    print("  PR #401 AUDIT — Trace-Back / Recall Readiness")
    print(f"  Ran {len(report.checks)} checks in {elapsed:.1f}s")
    print("=" * 74)
    print()

    sections = [
        "A. Engine Correctness",
        "B. API Contract",
        "C. Frontend Wiring",
        "D. Security & Guardrails",
        "E. Code Quality",
    ]

    for section in sections:
        earned, possible_sec = report.section_score(section)
        pct = (earned / possible_sec * 100) if possible_sec > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        section_checks = [c for c in report.checks if c.section == section]

        print(f"  ┌─ {section}  [{earned:.0f}/{possible_sec:.0f} pts]")
        print(f"  │  {bar} {pct:.0f}%")

        for c in section_checks:
            icon = "✅" if c.passed else ("⚠️ " if c.earned > 0 else "❌")
            pts = f"[{c.earned:.0f}/{c.max_points:.0f}]"
            print(f"  │  {icon} {pts:>7}  {c.name}")
            if not c.passed and c.detail:
                for line in c.detail.splitlines()[:3]:
                    print(f"  │           └─ {line[:70]}")

        print("  │")

    # Final grade
    pct_total = (total / possible * 100) if possible > 0 else 0
    if pct_total >= 90:
        grade = "SHIP IT ✅"
        color = "\033[92m"  # green
    elif pct_total >= 75:
        grade = "MINOR ISSUES ⚠️"
        color = "\033[93m"  # yellow
    elif pct_total >= 60:
        grade = "NEEDS WORK 🔧"
        color = "\033[93m"
    else:
        grade = "REJECT ❌"
        color = "\033[91m"  # red
    reset = "\033[0m"

    print("  ╔══════════════════════════════════════════════════════════════╗")
    print(f"  ║  FINAL SCORE:  {color}{total:.0f} / {possible:.0f}  ({pct_total:.0f}%){reset}                              ║")
    print(f"  ║  GRADE:        {color}{grade}{reset}                                  ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()

    # Failures summary
    failures = [c for c in report.checks if not c.passed]
    if failures:
        print(f"  {len(failures)} check(s) need attention:")
        for c in failures:
            print(f"    • {c.name}: {c.detail[:80]}")
        print()

    return int(pct_total >= 75)  # exit code: 0 = pass, 1 = fail


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    report = AuditReport(start_time=time.time())

    print("\n  🔍 Auditing PR #401 — Trace-Back / Recall Readiness ...\n")

    audit_engine_correctness(report)
    audit_api_contract(report)
    audit_frontend_wiring(report)
    audit_security(report)
    audit_code_quality(report)

    report.end_time = time.time()
    ok = render_report(report)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
