"""
Curated FSMA-only regulatory source list.

These are the canonical FDA/CFR sources for FSMA 204 compliance.
This is the single source of truth for what gets ingested nightly.

``load_fsma_sources`` is the only supported way to read that list for a
fetch. It refuses a malformed entry, a name that could escape a path or
the manual-upload queue record, a URL outside the FDA source hosts, and
any extra field such as a scope claim.
"""

import re
from collections.abc import Mapping
from typing import List, TypedDict
from urllib.parse import unquote, urlparse

from shared.url_validation import SSRFError, validate_url


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

# Closed manifest. Extra keys are scope claims and are rejected, not ignored.
_REQUIRED_FIELDS = ("name", "url", "type", "jurisdiction", "description")
_ALLOWED_FIELDS = frozenset(_REQUIRED_FIELDS)
_ALLOWED_TYPES = frozenset({"html", "pdf"})
_ALLOWED_JURISDICTION = "FDA"
_ALLOWED_SOURCE_DOMAINS = ["ecfr.gov", "fda.gov", "federalregister.gov"]
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_DESCRIPTION_LEN = 400
_MAX_URL_LEN = 2048


class PluginManifestError(ValueError):
    """The FSMA plugin catalog is malformed or asks for more than FDA scope."""


def _fail(index: int, reason: str) -> None:
    raise PluginManifestError(f"FSMA plugin manifest entry {index} is not usable: {reason}")


def _path_escapes(url: str) -> bool:
    """True when the URL path walks upward or carries a null byte."""
    path = unquote(urlparse(url).path)
    if "\\" in path or "\x00" in path:
        return True
    return any(segment == ".." for segment in path.split("/"))


def load_fsma_sources(entries: object | None = None) -> tuple[FsmaSource, ...]:
    """Return a copy of the FSMA catalog, or raise if any entry is unsafe.

    Checks are structural (closed fields, path-safe names, https, host
    allowlist). DNS and private-address refusal still happen at fetch time.
    """
    if entries is None:
        entries = FSMA_SOURCES
    if isinstance(entries, (str, bytes)) or not isinstance(entries, (list, tuple)):
        raise PluginManifestError("FSMA plugin manifest must be a list of entries")
    if len(entries) == 0:
        raise PluginManifestError("FSMA plugin manifest is empty")

    loaded: list[FsmaSource] = []
    seen_names: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, Mapping):
            _fail(index, "entry must be an object")
        unknown = sorted(str(key) for key in entry.keys() if key not in _ALLOWED_FIELDS)
        if unknown:
            _fail(index, f"unknown fields {unknown}")
        missing = [field for field in _REQUIRED_FIELDS if field not in entry]
        if missing:
            _fail(index, f"missing fields {missing}")

        name = entry["name"]
        url = entry["url"]
        source_type = entry["type"]
        jurisdiction = entry["jurisdiction"]
        description = entry["description"]
        if not all(isinstance(value, str) for value in (name, url, source_type, jurisdiction, description)):
            _fail(index, "name, url, type, jurisdiction, and description must be strings")

        if not _NAME_RE.fullmatch(name) or ".." in name:
            _fail(index, "name must be a short path-safe token")
        folded = name.casefold()
        if folded in seen_names:
            _fail(index, "duplicate name")
        seen_names.add(folded)

        if source_type not in _ALLOWED_TYPES:
            _fail(index, "type must be html or pdf")
        if jurisdiction != _ALLOWED_JURISDICTION:
            _fail(index, "jurisdiction must be FDA")

        if (
            not description.strip()
            or len(description) > _MAX_DESCRIPTION_LEN
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in description)
        ):
            _fail(index, "description must be a single line of text")

        if len(url) > _MAX_URL_LEN or "\\" in url or any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
            _fail(index, "url must be a single https address on an FDA source host")
        parsed = urlparse(url)
        if parsed.username is not None or parsed.password is not None:
            _fail(index, "url must not carry credentials")
        try:
            validate_url(
                url,
                allowed_schemes=frozenset({"https"}),
                allowed_domains=_ALLOWED_SOURCE_DOMAINS,
                resolve_dns=False,
            )
        except SSRFError as exc:
            _fail(index, f"url is outside the FDA source allowlist ({exc})")
        if _path_escapes(url):
            _fail(index, "url path escapes its directory")

        loaded.append(
            {
                "name": name,
                "url": url,
                "type": source_type,
                "jurisdiction": jurisdiction,
                "description": description,
            }
        )
    return tuple(loaded)


# Boot fails if the shipped list drifts out of the rules above.
load_fsma_sources(FSMA_SOURCES)
