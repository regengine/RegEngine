"""
Curated FSMA-only regulatory source list.

These are the canonical FDA/CFR sources for FSMA 204 compliance.
This is the single source of truth for what gets ingested nightly.
"""

from typing import List, TypedDict


class FsmaSource(TypedDict):
    name: str
    url: str
    type: str  # "html" | "pdf"
    jurisdiction: str
    description: str


FSMA_SOURCES: List[FsmaSource] = [
    # ── eCFR Title 21 (machine-readable, ETag-friendly) ──────────────────
    {
        "name": "21CFR-Part1",
        "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "General administrative regulations — definitions and scope",
    },
    {
        "name": "21CFR-Part11",
        "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Electronic records and electronic signatures",
    },
    {
        "name": "21CFR-Part117",
        "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-117",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Current Good Manufacturing Practice, Hazard Analysis, and Risk-Based Preventive Controls for Human Food",
    },
    {
        "name": "21CFR-Part204",
        "url": "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-204",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Requirements for Additional Traceability Records for Certain Foods (FSMA 204)",
    },
    # ── FDA Guidance Documents ────────────────────────────────────────────
    {
        "name": "FSMA-204-Traceability-Final-Rule",
        "url": "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "FSMA 204 final rule overview and compliance dates",
    },
    {
        "name": "FSMA-204-FTL-List",
        "url": "https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Food Traceability List — the 23 food categories subject to FSMA 204",
    },
    {
        "name": "FSMA-204-Guidance-CTE-KDE",
        "url": "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-204-key-requirements-food-traceability",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Key Requirements: Critical Tracking Events and Key Data Elements",
    },
    # ── Federal Register (rule change detection) ──────────────────────────
    {
        "name": "FederalRegister-FSMA-204",
        "url": "https://www.federalregister.gov/documents/search.json?conditions[term]=FSMA+204+traceability&conditions[agencies][]=food-and-drug-administration&order=newest",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Federal Register search for FSMA 204 rule changes — used for change detection",
    },
]
