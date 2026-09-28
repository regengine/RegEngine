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
    # Use the official renderer API. The public /current/... reader pages
    # 302 automated clients to unblock.federalregister.gov (bot wall).
    {
        "name": "21CFR-Part1",
        "url": "https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-21?chapter=I&subchapter=A&part=1",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "General administrative regulations — definitions and scope",
    },
    {
        "name": "21CFR-Part11",
        "url": "https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-21?chapter=I&subchapter=A&part=11",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Electronic records and electronic signatures",
    },
    {
        "name": "21CFR-Part117",
        "url": "https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-21?chapter=I&subchapter=B&part=117",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Current Good Manufacturing Practice, Hazard Analysis, and Risk-Based Preventive Controls for Human Food",
    },
    {
        # FSMA 204 is codified at 21 CFR Part 1 Subpart S (§1.1300-1.1465).
        # There is no 21 CFR Part 204 in eCFR (the old URL could never resolve).
        "name": "21CFR-Part1-SubpartS",
        "url": "https://www.ecfr.gov/api/renderer/v1/content/enhanced/current/title-21?chapter=I&subchapter=A&part=1&subpart=S",
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
        # FDA retired the HTML "key requirements" page (404); this is the
        # current published CTE/KDE reference sheet.
        "url": "https://www.fda.gov/files/food/published/FSMA%20Rule%20for%20Food%20Traceability%20-%202024-0520-CTEs-KDEs.pdf",
        "type": "pdf",
        "jurisdiction": "FDA",
        "description": "Key Requirements: Critical Tracking Events and Key Data Elements",
    },
    # ── Federal Register (rule change detection) ──────────────────────────
    {
        "name": "FederalRegister-FSMA-204",
        "url": "https://www.federalregister.gov/api/v1/documents.json?conditions[term]=FSMA+204+traceability&conditions[agencies][]=food-and-drug-administration&order=newest",
        "type": "html",
        "jurisdiction": "FDA",
        "description": "Federal Register search for FSMA 204 rule changes — used for change detection",
    },
]
