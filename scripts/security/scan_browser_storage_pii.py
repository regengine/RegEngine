#!/usr/bin/env python3
"""Detect likely PII persisted in browser local/session storage."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


STORAGE_CALL_START = re.compile(
    r"(?:window\.)?(?P<storage>localStorage|sessionStorage)\.setItem\s*\("
)

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


def _storage_calls(path: Path) -> Iterable[StorageCall]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return

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
    if not match:
        return None
    return match.group("key")


def _contains_any(text: str, terms: Iterable[str]) -> str | None:
    lowered = text.lower()
    return next((term for term in terms if term in lowered), None)


def inspect_call(call: StorageCall) -> Violation | None:
    if "pii-storage-allow" in call.text:
        return None

    key = _literal_storage_key(call.text)
    key_lower = key.lower() if key else ""

    if key_lower not in SAFE_STORAGE_KEYS:
        key_term = _contains_any(key_lower, SENSITIVE_KEY_TERMS)
        if key_term:
            return Violation(
                path=call.path,
                line_no=call.line_no,
                storage=call.storage,
                reason=f"storage key contains sensitive term '{key_term}'",
                snippet=call.text.strip().splitlines()[0],
            )

    value_context = call.text.lower()
    if key:
        value_context = value_context.replace(key_lower, "")

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


def scan_paths(paths: Iterable[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for path in _source_files(paths):
        for call in _storage_calls(path):
            violation = inspect_call(call)
            if violation:
                violations.append(violation)
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail when frontend browser storage persists likely PII."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["frontend/src"],
        help="Files or directories to scan. Defaults to frontend/src.",
    )
    args = parser.parse_args(argv)

    violations = scan_paths(Path(path) for path in args.paths)
    if not violations:
        print("Browser storage PII scan passed.")
        return 0

    print("Browser storage PII scan failed:")
    for violation in violations:
        print(
            f"{violation.path}:{violation.line_no}: "
            f"{violation.reason} in {violation.storage}.setItem"
        )
        print(f"  {violation.snippet}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
