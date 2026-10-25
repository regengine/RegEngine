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
and its column headers appear, verbatim, as headers on that FDA tab.
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
FDA_TEMPLATE_SHA256 = "632ed553b9f2f0a2705c59e94189fd63de45a9481478bea06390285f4f5212a4"
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


def fda_tab_text(pdf_bytes: bytes) -> dict[str, str]:
    """Return normalised header text per FDA tab, parsed from the PDF."""
    from pypdf import PdfReader

    tabs: dict[str, str] = {}
    for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
        text = _norm(page.extract_text() or "")
        idx = text.find(_TITLE)
        if idx < 0:
            continue
        rest = text[idx + len(_TITLE) :].strip()
        name = next((t for t in sorted(FDA_CTE_TABS + list(_NON_CTE_TABS), key=len, reverse=True) if rest.startswith(t)), None)
        if name is None or name in _NON_CTE_TABS:
            continue
        tabs[name] = (tabs.get(name, "") + " " + rest[len(name) :]).strip()
    return tabs


def regengine_tabs() -> dict[str, list[str]]:
    """Tabs RegEngine emits. The export is a single CSV with no tab name."""
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / "services"))
    sys.path.insert(0, str(repo / "services" / "compliance"))
    from app.fsma_spreadsheet import generate_fda_csv

    rows = list(csv.reader(io.StringIO(generate_fda_csv([]))))
    header = next(r for r in rows if r and r[0] == "Event Type (CTE)")
    return {"(single CSV, no tab)": header}


def compare(re_tabs: dict[str, list[str]], fda_tabs: dict[str, str]) -> dict:
    report = {"source": FDA_TEMPLATE_URL, "fda_tabs": list(fda_tabs), "tabs": [], "ok": True}
    for name, headers in re_tabs.items():
        fda_text = fda_tabs.get(name)
        missing = [h for h in headers if fda_text is None or _norm(h) not in fda_text]
        anywhere = [h for h in headers if any(_norm(h) in t for t in fda_tabs.values())]
        entry = {
            "regengine_tab": name,
            "fda_tab_exists": fda_text is not None,
            "header_count": len(headers),
            "mismatched_headers": missing,
            "headers_found_on_some_fda_tab": anywhere,
        }
        report["tabs"].append(entry)
        if missing or fda_text is None:
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
            print(f"{t['regengine_tab']}: FDA tab exists={t['fda_tab_exists']}, "
                  f"{len(t['mismatched_headers'])}/{t['header_count']} headers mismatch, "
                  f"{len(t['headers_found_on_some_fda_tab'])} appear on some FDA tab")
        print(f"FDA tabs not emitted: {len(report['fda_tabs_not_emitted'])}/{len(report['fda_tabs'])}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
