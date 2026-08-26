#!/usr/bin/env python3
"""Validate sanitized, deployment-bound security release evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.router_policy import PRODUCTION_ENABLED_ROUTERS  # noqa: E402

DEFAULT_EVIDENCE_DIR = ROOT / "docs" / "security" / "release-evidence"
ALLOWED_RESULTS = {"pass", "fail", "not_run"}
REQUIRED_APPROVAL_CHECKS = {
    "rls_runtime_roles",
    "route_manifest",
    "two_tenant_matrix",
    "administrative_authentication",
    "replica_revocation",
    "email_enumeration",
    "csrf_ssrf",
    "deployment_docs",
    "deployment_environment_contract",
    "security_txt_external",
    "alembic_drift",
}
FORBIDDEN_FIELD_NAMES = {
    "secret",
    "secret_value",
    "password",
    "token",
    "token_value",
    "raw_key",
    "credential",
    "credential_value",
    "api_key",
    "api_key_value",
}
SECRET_VALUE_PATTERNS = (
    re.compile(r"\brge_(?:live|test)_[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9_-]{8,}"),
    re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s:/]+:[^\s@]+@", re.IGNORECASE),
)


def _walk(value: Any, *, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_FIELD_NAMES:
                errors.append(f"{path}.{key}: secret-bearing field names are forbidden")
            errors.extend(_walk(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_walk(child, path=f"{path}[{index}]"))
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS):
            errors.append(f"{path}: value resembles secret material")
    return errors


def validate_record(record: dict[str, Any]) -> list[str]:
    errors = _walk(record)
    for field in ("schema_version", "release_id", "status", "verification_date"):
        if field not in record:
            errors.append(f"$.{field}: required field missing")

    if record.get("schema_version") != 1:
        errors.append("$.schema_version: expected 1")
    if record.get("status") not in {"not_approved", "approved"}:
        errors.append("$.status: expected not_approved or approved")
    try:
        date.fromisoformat(str(record.get("verification_date")))
    except ValueError:
        errors.append("$.verification_date: expected YYYY-MM-DD")

    expected_routers = set(PRODUCTION_ENABLED_ROUTERS)
    actual_routers = set(record.get("enabled_routers") or [])
    if actual_routers != expected_routers:
        errors.append(
            "$.enabled_routers: must exactly match production policy "
            f"(missing={sorted(expected_routers - actual_routers)}, "
            f"extra={sorted(actual_routers - expected_routers)})"
        )

    env_names = record.get("environment_variable_names") or []
    if not isinstance(env_names, list) or any(
        not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) for name in env_names
    ):
        errors.append("$.environment_variable_names: names only; values and assignments are forbidden")

    checks = record.get("checks") or []
    check_map: dict[str, str] = {}
    if not isinstance(checks, list):
        errors.append("$.checks: expected list")
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(f"$.checks[{index}]: expected object")
                continue
            check_id = check.get("id")
            result = check.get("result")
            if not isinstance(check_id, str) or not check_id:
                errors.append(f"$.checks[{index}].id: required")
            if result not in ALLOWED_RESULTS:
                errors.append(f"$.checks[{index}].result: expected one of {sorted(ALLOWED_RESULTS)}")
            if isinstance(check_id, str) and check_id:
                if check_id in check_map:
                    errors.append(f"$.checks[{index}].id: duplicate check id {check_id!r}")
                check_map[check_id] = str(result)

    approved = record.get("status") == "approved"
    if bool(record.get("release_approved")) != approved:
        errors.append("$.release_approved: must agree with status")

    bindings = (
        ("frontend", "git_sha"),
        ("frontend", "deployment_id"),
        ("backend", "git_sha"),
        ("backend", "deployment_id"),
    )
    if approved:
        for section, field in bindings:
            value = (record.get(section) or {}).get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"$.{section}.{field}: required for approval")
        revision = record.get("alembic_revision")
        if not isinstance(revision, str) or not revision.strip() or revision == "not_verified":
            errors.append("$.alembic_revision: verified migration head required for approval")
        for check_id in sorted(REQUIRED_APPROVAL_CHECKS):
            if check_map.get(check_id) != "pass":
                errors.append(f"$.checks: {check_id} must pass for approval")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.paths or sorted(DEFAULT_EVIDENCE_DIR.glob("*.json"))
    if not paths:
        print("No release-evidence records found.", file=sys.stderr)
        return 1

    failures: list[str] = []
    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"{path}: {exc}")
            continue
        for error in validate_record(record):
            failures.append(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}: {error}")

    if failures:
        print("Release-evidence validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Validated {len(paths)} sanitized release-evidence record(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
