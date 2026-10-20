"""What may leave the machine: a refusal check for everything the lab sends to Jev or Claude.

The jev-sidecar rules apply (``.claude/skills/jev-sidecar/SKILL.md``, "Never
send"): no secrets, no customer data, no personal data. Header names,
synthetic examples and question wording are fine. :func:`findings` names
what it found by kind and location, never by value, so a refusal message can
be shown and logged without repeating the secret it caught.

It is a guard against mistakes, not a proof of absence: a value that matches
none of the patterns still leaves. Paste header rows and synthetic examples,
not exports.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("credentials in a URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@", re.IGNORECASE)),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    (
        "Slack token or webhook",
        re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}|hooks\.slack\.com/services/", re.IGNORECASE),
    ),
    ("API key", re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}")),
    (
        "secret assignment",
        re.compile(r"\b(?:api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*['\"]?[^\s'\"]{6,}", re.IGNORECASE),
    ),
)
# A long run of key-like characters with letters and digits mixed: most API
# keys and tokens look like this; header names and prose do not.
_OPAQUE_TOKEN = re.compile(r"[A-Za-z0-9_\-+/=]{32,}")
# The patterns of ``shared.pii.redact_pii`` (SSN, phone, email, street
# address), except that the street suffix must be its own word within four
# words of the house number: redact_pii's pattern reads "FSMA 204 ... record"
# as an address ("rd"), which is fine for short sample values and wrong for
# question wording.
_PERSONAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(
        r"\b\d{1,5}(?:\s+[A-Za-z0-9.'-]+){1,4}\s+"
        r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way|Place|Pl)\b",
        re.IGNORECASE,
    ),
)
_CUSTOMER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GLN or GTIN number", re.compile(r"(?<!\d)\d{13,14}(?!\d)")),
    (
        "UUID (tenant or record id)",
        re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    ),
)


def strings(
    value: Any, path: str = "$", *, name_key: Callable[[str], bool] = lambda key: True
) -> Iterable[tuple[str, str]]:
    """Every string in a JSON-like value, keys included, with a JSONPath-ish location.

    A key appears in a location only when ``name_key`` allows it; otherwise
    the location gives the key's position, so a key that must not leave
    (a labelled header that holds a secret) is never repeated by the reason.
    """
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for index, (key, item) in enumerate(value.items(), start=1):
            shown = f"{path}.{key}" if name_key(str(key)) else f"{path}.<key {index}>"
            yield shown, str(key)
            yield from strings(item, shown, name_key=name_key)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from strings(item, f"{path}[{index}]", name_key=name_key)
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, int) or (isinstance(value, float) and value.is_integer()):
        # A GLN, GTIN or phone number pasted as a JSON number is still one.
        yield path, str(int(value))
    elif not isinstance(value, float):
        yield path, json.dumps(value, default=str)


def _personal(text: str) -> bool:
    return any(pattern.search(text) for pattern in _PERSONAL_PATTERNS)


def _looks_opaque(text: str) -> bool:
    for match in _OPAQUE_TOKEN.finditer(text):
        token = match.group(0)
        if any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
            return True
    return False


# Environment variables whose values are credentials. Their values are
# compared in memory only; a finding names the variable, never the value.
_SECRET_ENV_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|DSN|DATABASE_URL", re.IGNORECASE)
_MIN_SECRET_ENV_CHARS = 8
# Cells that look like row values rather than column names: dates, numbers,
# and single-token codes with a run of three or more digits (lot codes,
# order numbers). Column names almost never look like any of these, so one
# such cell is enough to refuse the row.
_VALUE_CELL = re.compile(r"^\s*(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|[-+]?\d[\d,]*(?:\.\d+)?|\d{4,}\S*)\s*$")
_CODE_CELL = re.compile(r"^\s*(?=\S*\d{3})[A-Za-z0-9]+(?:[-/._#][A-Za-z0-9]+)*\s*$")


def _secret_env_values(environ: Mapping[str, str] | None = None) -> list[tuple[str, str]]:
    source = os.environ if environ is None else environ
    return [
        (name, value)
        for name, value in source.items()
        if _SECRET_ENV_NAME.search(name) and len(value.strip()) >= _MIN_SECRET_ENV_CHARS
    ]


def data_row_findings(headers: Sequence[str]) -> list[str]:
    """A refusal reason when any cell of ``headers`` looks like a value rather than a column name.

    The reason gives cell positions (1-based), never their content.
    """
    positions = [
        index
        for index, cell in enumerate((str(cell) for cell in headers), start=1)
        if cell.strip() and (_VALUE_CELL.match(cell) or _CODE_CELL.match(cell) or _personal(cell))
    ]
    if not positions:
        return []
    listed = ", ".join(str(index) for index in positions[:12])
    return [f"cell(s) {listed} look like values (dates, numbers or codes), not column names: paste only the header row"]


def value_findings(value: Any, *, codes: bool = True) -> list[str]:
    """``"looks like a value ... at <location>"`` for every string in ``value`` that reads as a row value.

    For a labelled row's labels, mappings and id, which a validation message
    would repeat: a lot code, an SSCC or a date pasted where a label belongs is
    refused by location before any message could repeat it. A key that looks
    like a value is given by position, as in :func:`findings`. With
    ``codes=False`` only dates and numbers count (an id such as
    ``local-3f9a8b7c6d5e`` holds digits by design).
    """

    def value_like(text: str) -> bool:
        return bool(text.strip()) and bool(_VALUE_CELL.match(text) or (codes and _CODE_CELL.match(text)))

    return [
        f"looks like a value (date, number or code), not a label at {location}"
        for location, text in strings(value, name_key=lambda key: not value_like(key))
        if value_like(text)
    ]


def _kinds(text: str, secrets_in_env: Sequence[tuple[str, str]]) -> list[str]:
    """What in ``text`` must not leave, by kind. Empty: nothing."""
    found: list[str] = []
    for name, secret in secrets_in_env:
        if secret in text:
            found.append(f"the value of {name}")
    for kind, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            found.append(kind)
    if _looks_opaque(text):
        found.append("key-like token")
    if _personal(text):
        found.append("personal data (email, phone, SSN or street address)")
    for kind, pattern in _CUSTOMER_PATTERNS:
        if pattern.search(text):
            found.append(kind)
    return found


def findings(value: Any, *, environ: Mapping[str, str] | None = None) -> list[str]:
    """``"<kind> at <location>"`` for everything in ``value`` that must not leave. Empty: it may.

    A location never repeats content that must not leave: a key with a
    finding of its own is given by position (``$.mappings.<key 2>``).
    """
    secrets_in_env = _secret_env_values(environ)
    found: list[str] = []
    for location, text in strings(value, name_key=lambda key: not _kinds(key, secrets_in_env)):
        found += [f"{kind} at {location}" for kind in _kinds(text, secrets_in_env)]
    return list(dict.fromkeys(found))


class Refused(ValueError):
    """The content may not leave the machine. ``reasons`` never repeat the content."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("refused: " + "; ".join(reasons))


def check(value: Any) -> None:
    reasons = findings(value)
    if reasons:
        raise Refused(reasons)
