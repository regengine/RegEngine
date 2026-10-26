#!/usr/bin/env python3
"""Compare RegEngine's FDA sortable spreadsheet headers with FDA's template.

Source of truth
---------------
FDA, "FSMA Food Traceability Rule: downloadable, electronic, sortable
spreadsheet template", https://www.fda.gov/media/179616/download
(fetched 2026-10-25; FDA serves a 50-page PDF at that URL, not an xlsx;
sha256 632ed553b9f2f0a2705c59e94189fd63de45a9481478bea06390285f4f5212a4).

The template has one tab per critical tracking event (CTE). This check
fails unless every tab RegEngine emits has the same name as an FDA tab
and each column header equals a whole header cell on that FDA tab
(header row only; body text and fragments of longer labels do not count).
The spreadsheet supports the 24-hour records request in
21 CFR 1.1455(c)(1).

Usage::

    python scripts/check_fda_spreadsheet_headers.py            # download
    python scripts/check_fda_spreadsheet_headers.py --pdf f.pdf
    python scripts/check_fda_spreadsheet_headers.py --json

Exit code 0 means every RegEngine tab matches; 1 means a mismatch.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

FDA_TEMPLATE_URL = "https://www.fda.gov/media/179616/download"
# Public SHA-256 of the FDA template download, not a credential.
FDA_TEMPLATE_SHA256 = "632ed553b9f2f0a2705c59e94189fd63de45a9481478bea06390285f4f5212a4"  # pragma: allowlist secret
_TITLE = "sortable spreadsheet template"

# CTE tabs in FDA's template, in template order (page titles of the PDF).
FDA_CTE_TABS = [
    "Harvesting",
    "Cooling",
    "Initial Packing",
    "Initial Packing Sprouts",
    "Initial Packing from Exempt",
    "First Land-Based Receiving",
    "Shipping",
    "Receiving",
    "Receiving From Exempt",
    "Transformation",
    "Farm Purchase by RFE or Rest.",
    "Ad-hoc RFE or Rest. Purchase",
    "Farm to School or Institution",
]
_NON_CTE_TABS = {"Introduction", "Definitions"}


def _norm(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u2010", "-").replace("\u2011", "-")
    return re.sub(r"\s+", " ", text).strip()


_BODY_MARKER = "Enter your KDEs Here"


def _header_lines(region: str) -> list[str]:
    return [ln for ln in (_norm(x) for x in region.splitlines()) if ln]


def fda_tab_text(pdf_bytes: bytes) -> dict[str, list[str]]:
    """Return the column-header lines per FDA tab, parsed from the PDF.

    Only the header row is kept: text after the first body placeholder
    ("Enter your KDEs Here") or page footer is dropped, so prose and body
    cells can never satisfy a header check.
    """
    from pypdf import PdfReader

    tab_names = sorted(FDA_CTE_TABS + list(_NON_CTE_TABS), key=len, reverse=True)
    tabs: dict[str, list[str]] = {}
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        raw = (page.extract_text() or "").replace("\xa0", " ")
        flat = _norm(raw)
        idx = flat.find(_TITLE)
        if idx < 0:
            continue
        rest = flat[idx + len(_TITLE) :].strip()
        name = next((t for t in tab_names if rest.startswith(t)), None)
        if name is None or name in _NON_CTE_TABS:
            continue
        lines = raw.splitlines()
        start = next(i for i, ln in enumerate(lines) if _TITLE in _norm(ln)) + 1
        region = "\n".join(lines[start:]).split(_BODY_MARKER, 1)[0]
        tabs.setdefault(name, []).extend(_header_lines(region))
    return tabs


def _is_header_cell(header: str, lines: list[str]) -> bool:
    """True if ``header`` equals a whole run of consecutive header lines.

    A fragment of a longer line (e.g. "Lot" inside "Traceability Lot Code")
    does not count; only complete header-line runs do.
    """
    target = _norm(header)
    n = len(lines)
    for i in range(n):
        joined = ""
        for j in range(i, n):
            joined = f"{joined} {lines[j]}".strip()
            if joined == target:
                return True
            if len(joined) >= len(target):
                break
    return False


def _find_header_row(rows: list[list[str]]) -> list[str]:
    """Header row of the export: the first non-empty row after the blank
    line that ends the preamble. Does not depend on any specific label."""
    for i, row in enumerate(rows):
        if not any(cell.strip() for cell in row) and i + 1 < len(rows):
            return rows[i + 1]
    raise ValueError("export has no blank line before its header row")


def regengine_tabs(events: list[dict] | None = None) -> dict[str, list[str]]:
    """Tabs RegEngine emits for ``events``. The export is a single CSV with no tab name."""
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "services"))
    sys.path.insert(0, str(repo / "services" / "compliance"))
    from app.fsma_spreadsheet import generate_fda_csv

    rows = list(csv.reader(io.StringIO(generate_fda_csv(events or []))))
    return {"(single CSV, no tab)": _find_header_row(rows)}


def compare(re_tabs: dict[str, list[str]], fda_tabs: dict[str, list[str]]) -> dict:
    """Match each RegEngine header against the FDA tab's header cells."""
    report = {"source": FDA_TEMPLATE_URL, "fda_tabs": list(fda_tabs), "tabs": [], "ok": True}
    for name, headers in re_tabs.items():
        fda_lines = fda_tabs.get(name)
        missing = [h for h in headers if fda_lines is None or not _is_header_cell(h, fda_lines)]
        anywhere = [h for h in headers if any(_is_header_cell(h, ls) for ls in fda_tabs.values())]
        report["tabs"].append(
            {
                "regengine_tab": name,
                "fda_tab_exists": fda_lines is not None,
                "header_count": len(headers),
                "mismatched_headers": missing,
                "headers_found_on_some_fda_tab": anywhere,
            }
        )
        if missing or fda_lines is None:
            report["ok"] = False
    report["fda_tabs_not_emitted"] = [t for t in fda_tabs if t not in re_tabs]
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", type=Path, help="local copy of FDA's template")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.pdf:
        data = args.pdf.read_bytes()
    else:
        req = urllib.request.Request(FDA_TEMPLATE_URL, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=60).read()
    import hashlib

    digest = hashlib.sha256(data).hexdigest()
    if digest != FDA_TEMPLATE_SHA256:
        print(f"warning: FDA template changed (sha256 {digest}); re-review FDA_CTE_TABS", file=sys.stderr)
    report = compare(regengine_tabs(), fda_tab_text(data))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for t in report["tabs"]:
            print(
                f"{t['regengine_tab']}: FDA tab exists={t['fda_tab_exists']}, "
                f"{len(t['mismatched_headers'])}/{t['header_count']} headers mismatch, "
                f"{len(t['headers_found_on_some_fda_tab'])} appear on some FDA tab header"
            )
        print(f"FDA tabs not emitted: {len(report['fda_tabs_not_emitted'])}/{len(report['fda_tabs'])}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
