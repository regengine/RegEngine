#!/usr/bin/env python3
"""Detect likely PII persisted in browser local/session storage.

Coverage: every write form is inspected, not just setItem calls: property
assignment (localStorage.email = ...) and bracket assignment
(localStorage["email"] = ...) persist exactly like setItem and are flagged
the same way. Reads (getItem, bracket reads, comparisons) never match because
every write pattern requires a bare ``=`` after the key.

Suppressions: the ONLY way to silence a finding is an inline marker carrying
a reason (``pii-storage-allow: <reason>``). A bare marker with no reason does
not suppress. Every applied suppression is collected and printed by main, so
the full suppression list appears in one place in CI logs for review.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

STORAGE_CALL_START = re.compile(r"(?:window\.)?(?P<storage>localStorage|sessionStorage)\.setItem\s*\(")
STORAGE_PROP_WRITE = re.compile(
    r"(?:window\.)?(?P<storage>localStorage|sessionStorage)\s*\.\s*(?P<key>[A-Za-z_$][\w$]*)\s*=(?![=>])"
)
STORAGE_INDEX_WRITE = re.compile(
    r"(?:window\.)?(?P<storage>localStorage|sessionStorage)\s*\[\s*(?P<quote>['\"`])(?P<key>.*?)(?P=quote)\s*\]\s*=(?![=>])"
)
SUPPRESSION_RE = re.compile(r"pii-storage-allow\s*:\s*(?P<reason>\S(?:.*\S)?)")

SENSITIVE_KEY_TERMS = (
    "access_token",
    "api_key",
    "company",
    "email",
    "lead",
    "password",
    "phone",
    "secret",
)

SENSITIVE_VALUE_TERMS = (
    "access_token",
    "api_key",
    "blob",
    "company",
    "email",
    "lead",
    "password",
    "phone",
    "photo",
    "raw_scan",
    "secret",
)

SAFE_STORAGE_KEYS = {
    "fsma_gap_analysis_retry",
    "fsma_gap_analysis_submitted",
    "re_lead_captured",
    "retailer_supplier_lead_retry",
    "retailer_supplier_lead_submitted",
}

SKIPPED_PARTS = {
    "__tests__",
    "node_modules",
    ".next",
    "coverage",
    "dist",
    "build",
}


@dataclass(frozen=True)
class StorageCall:
    path: Path
    line_no: int
    storage: str
    text: str


@dataclass(frozen=True)
class Violation:
    path: Path
    line_no: int
    storage: str
    reason: str
    snippet: str


@dataclass(frozen=True)
class Suppression:
    path: Path
    line_no: int
    storage: str
    reason: str


def _is_skipped(path: Path) -> bool:
    return bool(SKIPPED_PARTS.intersection(path.parts)) or path.name.endswith(
        (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
    )


def _source_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            for child in path.rglob("*"):
                if child.suffix in {".js", ".jsx", ".ts", ".tsx"} and not _is_skipped(child):
                    yield child
        elif path.is_file() and path.suffix in {".js", ".jsx", ".ts", ".tsx"}:
            if not _is_skipped(path):
                yield path


def _paren_delta(text: str) -> int:
    in_quote: str | None = None
    escaped = False
    delta = 0

    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if in_quote:
            if char == in_quote:
                in_quote = None
            continue
        if char in {"'", '"', "`"}:
            in_quote = char
            continue
        if char == "(":
            delta += 1
        elif char == ")":
            delta -= 1
    return delta


def _read_lines(path: Path) -> tuple[list[str] | None, str | None]:
    """Return (lines, error). A file that cannot be read reports its error so
    callers can record it as a finding instead of passing silently."""
    try:
        return path.read_text(encoding="utf-8").splitlines(), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, str(exc)


def _write_calls_in_lines(path: Path, lines: list[str]) -> Iterable[StorageCall]:
    for index, line in enumerate(lines):
        prop_match = STORAGE_PROP_WRITE.search(line)
        if prop_match and prop_match.group("key") not in {
            "setItem",
            "getItem",
            "removeItem",
            "clear",
            "key",
            "length",
        }:
            yield StorageCall(
                path=path,
                line_no=index + 1,
                storage=prop_match.group("storage"),
                text=line.strip(),
            )
            continue
        index_match = STORAGE_INDEX_WRITE.search(line)
        if index_match:
            yield StorageCall(
                path=path,
                line_no=index + 1,
                storage=index_match.group("storage"),
                text=line.strip(),
            )


def _set_item_calls_in_lines(path: Path, lines: list[str]) -> Iterable[StorageCall]:

    index = 0
    while index < len(lines):
        line = lines[index]
        match = STORAGE_CALL_START.search(line)
        if not match:
            index += 1
            continue

        call_lines = [line]
        balance = _paren_delta(line[match.start() :])
        end = index
        while balance > 0 and end + 1 < len(lines):
            end += 1
            call_lines.append(lines[end])
            balance += _paren_delta(lines[end])

        yield StorageCall(
            path=path,
            line_no=index + 1,
            storage=match.group("storage"),
            text="\n".join(call_lines),
        )
        index = end + 1


def _literal_storage_key(call_text: str) -> str | None:
    match = re.search(
        r"setItem\s*\(\s*(?P<quote>['\"`])(?P<key>.*?)(?P=quote)",
        call_text,
        flags=re.DOTALL,
    )
    if match:
        return match.group("key")
    match = STORAGE_INDEX_WRITE.search(call_text)
    if match:
        return match.group("key")
    match = STORAGE_PROP_WRITE.search(call_text)
    if match:
        return match.group("key")
    return None


def _words(text: str) -> set[str]:
    """Split text into lowercase words on every non-alphanumeric boundary,
    treating underscores and lower-to-Upper transitions as separators, so
    snake_case and camelCase identifiers match by whole word."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return {word.lower() for word in re.split(r"[^A-Za-z0-9]+", spaced) if word}


def _contains_any(text: str, terms: Iterable[str]) -> str | None:
    words = _words(text)
    return next((term for term in terms if term in words), None)


def find_suppression(call_text: str) -> str | None:
    """Return the stated reason when a suppression marker with a reason is
    present, else None. A bare marker with no reason suppresses nothing."""
    match = SUPPRESSION_RE.search(call_text)
    if not match:
        return None
    return match.group("reason")


def inspect_call(call: StorageCall) -> Violation | None:
    if find_suppression(call.text) is not None:
        return None

    key = _literal_storage_key(call.text)
    key_lower = key.lower() if key else ""

    if key_lower not in SAFE_STORAGE_KEYS:
        key_term = _contains_any(key or "", SENSITIVE_KEY_TERMS)
        if key_term:
            return Violation(
                path=call.path,
                line_no=call.line_no,
                storage=call.storage,
                reason=f"storage key contains sensitive term '{key_term}'",
                snippet=call.text.strip().splitlines()[0],
            )

    value_context = call.text
    if key:
        value_context = re.sub(re.escape(key), "", value_context, flags=re.IGNORECASE)

    value_term = _contains_any(value_context, SENSITIVE_VALUE_TERMS)
    if value_term:
        return Violation(
            path=call.path,
            line_no=call.line_no,
            storage=call.storage,
            reason=f"stored value expression contains sensitive term '{value_term}'",
            snippet=call.text.strip().splitlines()[0],
        )

    return None


def _calls_in_file(path: Path) -> tuple[list[StorageCall], str | None]:
    lines, error = _read_lines(path)
    if error is not None or lines is None:
        return [], error
    calls = list(_set_item_calls_in_lines(path, lines))
    seen = {(call.line_no, call.text) for call in calls}
    for call in _write_calls_in_lines(path, lines):
        if (call.line_no, call.text) not in seen:
            seen.add((call.line_no, call.text))
            calls.append(call)
    return calls, None


def scan_paths_with_suppressions(
    paths: Iterable[Path],
) -> tuple[list[Violation], list[Suppression]]:
    """Return (violations, applied suppressions). Files that cannot be read
    are reported as violations (fail closed). Every applied suppression is
    collected here so main can print one central review trail."""
    violations: list[Violation] = []
    suppressions: list[Suppression] = []
    for path in _source_files(paths):
        calls, error = _calls_in_file(path)
        if error is not None:
            violations.append(
                Violation(
                    path=path,
                    line_no=0,
                    storage="",
                    reason=f"unreadable file treated as a finding: {error}",
                    snippet="",
                )
            )
            continue
        for call in calls:
            suppression_reason = find_suppression(call.text)
            if suppression_reason is not None:
                suppressions.append(
                    Suppression(
                        path=call.path,
                        line_no=call.line_no,
                        storage=call.storage,
                        reason=suppression_reason,
                    )
                )
                continue
            violation = inspect_call(call)
            if violation:
                violations.append(violation)
    return violations, suppressions


def scan_paths(paths: Iterable[Path]) -> list[Violation]:
    violations, _ = scan_paths_with_suppressions(paths)
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail when frontend browser storage persists likely PII.")
    parser.add_argument(
        "paths",
        nargs="*",
        default=["frontend/src"],
        help="Files or directories to scan. Defaults to frontend/src.",
    )
    args = parser.parse_args(argv)

    violations, suppressions = scan_paths_with_suppressions(Path(path) for path in args.paths)
    if suppressions:
        print(f"Suppressed {len(suppressions)} storage write(s) via pii-storage-allow (central trail):")
        for suppression in suppressions:
            print(f"{suppression.path}:{suppression.line_no}: {suppression.reason}")
    if not violations:
        print("Browser storage PII scan passed.")
        return 0

    print("Browser storage PII scan failed:")
    for violation in violations:
        location = f"{violation.path}:{violation.line_no}"
        if violation.storage:
            location += f": {violation.reason} in {violation.storage}.setItem"
        else:
            location += f": {violation.reason}"
        print(location)
        if violation.snippet:
            print(f"  {violation.snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
