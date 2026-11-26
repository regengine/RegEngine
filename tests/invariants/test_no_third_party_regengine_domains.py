"""Drift guard: production code must not point at domains RegEngine does not own.

regengine.ai and regengine.dev are live third-party sites, regengine.com is
registered to a third party, and regengine.io is unconfirmed. Code that builds
a label QR URL, an agent inbox address, a User-Agent or an actor email on one of
those domains sends scans, mail or crawler contact traffic to a stranger.
RegEngine's own domain is regengine.co.

Scope is source code only (``server/``, ``services/``, ``frontend/src``).
Tests, fixtures, docs and historical records may still mention the other
domains, so they are skipped.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("server", "services", "frontend/src")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs"}
SKIP_DIRS = {"node_modules", "tests", "__tests__", "__pycache__", "dist", "build", "venv"}
THIRD_PARTY_DOMAIN = re.compile(r"regengine\.(?:ai|dev|io|com)\b", re.IGNORECASE)


def _source_files():
    for root in SCAN_ROOTS:
        for dirpath, dirnames, filenames in os.walk(REPO_ROOT / root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix not in SOURCE_SUFFIXES or ".test." in name or ".spec." in name:
                    continue
                yield path


def test_pattern_flags_third_party_domains_and_spares_ours():
    for bad in (
        "https://trace.regengine.ai",
        "bot@agents.acme.regengine.dev",
        "admin@regengine.io",
        "+https://REGENGINE.COM",
    ):
        assert THIRD_PARTY_DOMAIN.search(bad), bad
    for ok in ("https://regengine.co", "support@regengine.co", "regengine.community"):
        assert not THIRD_PARTY_DOMAIN.search(ok), ok


def test_scan_covers_the_files_that_used_to_hold_third_party_domains():
    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in _source_files()}
    for expected in (
        "server/main.py",
        "services/graph/app/routers/labels.py",
        "services/shared/agent_org/providers.py",
        "services/ingestion/app/routes_ingest.py",
        "services/ingestion/app/regulation_parser.py",
        "frontend/src/app/compliance/snapshots/page.tsx",
    ):
        assert expected in scanned, f"scan no longer reaches {expected}"


def test_production_source_has_no_third_party_regengine_domains():
    hits = []
    for path in _source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if THIRD_PARTY_DOMAIN.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}: {line.strip()[:120]}")
    assert not hits, "third-party regengine domain in production source:\n" + "\n".join(hits)
