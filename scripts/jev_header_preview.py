#!/usr/bin/env python3
"""Preview TypeSafe Jev header-mapping suggestions for a local CSV file.

Runs the code ``POST /api/v1/ingest/csv`` runs before it parses rows
(``_suggest_header_mappings_for_upload`` in
``services/ingestion/app/csv_templates.py``): the same recognised-column
vocabulary, the same request to Jev, the same confidence bands and apply
policy. Nothing is ingested, persisted or queued, and no database is used.

    python3 scripts/jev_header_preview.py supplier.csv
    python3 scripts/jev_header_preview.py supplier.csv --json
    python3 scripts/jev_header_preview.py supplier.csv --sample-values 2 --simulate-apply
    python3 scripts/jev_header_preview.py supplier.csv --prompt-key
    python3 scripts/jev_header_preview.py supplier.csv --cte-type shipping

Configuration comes from the environment through ``shared.jev.JevSettings``
(``TYPESAFE_API_KEY``, ``TYPESAFE_DEFAULT_MODEL``, ``TYPESAFE_BASE_URL`` and
the ``REGENGINE_JEV_*`` variables; see docs/engineering/JEV_HEADER_MAPPING.md).
``--prompt-key`` reads the key with ``getpass`` instead (hidden on a
terminal; read from stdin otherwise), for this run only. The script never
prints, logs or writes the key.

What leaves the process is what production sends: the header row, the
declared CTE when ``--cte-type`` is given (the route's ``cte_type`` form
field, accepting the same values) and no row can contradict it (the
report says when it was withheld and why), plus PII-redacted sample
values per unrecognised column only when ``--sample-values`` (or
``REGENGINE_JEV_HEADER_SAMPLE_VALUES``) is above 0. Rows are never sent.

Exit codes:
    0  suggestions received, or no unrecognised headers (no request made)
    1  bad usage; unreadable, oversized or non-UTF-8 file; no header row; malformed header
       row (status malformed_header: nothing is sent, with or without a key); unexpected error
    2  Jev not configured (no TYPESAFE_API_KEY) or switched off (REGENGINE_JEV_ENABLED)
    3  Jev unavailable (auth, rate limit, timeout, connection, server error, ...)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import dataclasses
import getpass
import json
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import structlog

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "services" / "ingestion", ROOT / "services"):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)


# Import-time notices from modules the route imports. This script never opens a
# database or a rate limiter, so they are noise here.
_IRRELEVANT_IMPORT_NOTICES = frozenset({"database_url_default", "rate_limit_redis_not_configured"})


def _drop_irrelevant_import_notices(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if event_dict.get("event") in _IRRELEVANT_IMPORT_NOTICES:
        raise structlog.DropEvent
    return event_dict


def _configure_cli_logging() -> None:
    """Send log output to stderr, warnings and above, so stdout carries only the preview.

    structlog's default logger prints to stdout, which would corrupt ``--json``
    output. Configuration warnings such as ``jev.settings.invalid`` and the
    wrapper's ``jev.unavailable`` line still show. Only called when run as a
    script: importing this module (tests) changes no global logging state.
    """
    # An explicit chain, not structlog's defaults: the default ConsoleRenderer
    # uses rich tracebacks with local variables, which would print every
    # frame's locals (settings, request bodies) on an unexpected exception.
    # format_exc_info renders a plain traceback, as the services' own logging
    # configuration does.
    structlog.configure(
        processors=[
            _drop_irrelevant_import_notices,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False, exception_formatter=structlog.dev.plain_traceback),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


if __name__ == "__main__":  # before the imports below can log anything
    _configure_cli_logging()

from app import csv_templates as route  # noqa: E402
from app.shared.upload_limits import MAX_CSV_FILE_SIZE_BYTES  # noqa: E402
from shared.jev import JevDecider, JevSettings  # noqa: E402
from shared.jev.header_mapping import MALFORMED_HEADER, HeaderMappingResult, unrecognized_headers  # noqa: E402
from shared.jev.settings import (  # noqa: E402
    API_KEY_ENV,
    APPLY_HEADER_MAPPINGS_ENV,
    ENABLED_ENV,
    HEADER_SAMPLE_VALUES_ENV,
    MAX_HEADER_SAMPLE_VALUES,
    MAX_RETRIES_ENV,
    TIMEOUT_ENV,
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_CONFIGURED = 2
EXIT_UNAVAILABLE = 3

PROG = "jev_header_preview"
KEY_PROMPT = "TypeSafe API key (hidden when typed at a terminal): "

_UNAVAILABLE_HINTS = {
    "auth": f"The vendor rejected the key (401/403): check {API_KEY_ENV}.",
    "rate_limited": f"Rate limited (429) after retries: wait and re-run, or raise {MAX_RETRIES_ENV}.",
    "timeout": f"Timed out: re-run, or raise {TIMEOUT_ENV} (seconds per attempt).",
    "connection": "Could not reach the API: check network, proxy and TYPESAFE_BASE_URL.",
    "server_error": "Vendor-side 5xx: re-run later.",
    "invalid_response": "The vendor response did not match the SDK schema: re-run later or check the SDK version.",
    "bad_request": "The vendor rejected the request (400/422): check TYPESAFE_DEFAULT_MODEL.",
    "api_error": "Unexpected vendor HTTP status: see the jev.unavailable line above for the status code.",
    "sdk_error": "The SDK refused before sending (for example a key containing spaces or non-ASCII characters).",
}


class _UsageError(Exception):
    """Bad arguments or an unusable file: exit 1."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)


def _sample_count(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be an integer from 0 to {MAX_HEADER_SAMPLE_VALUES}") from None
    if not 0 <= value <= MAX_HEADER_SAMPLE_VALUES:
        raise argparse.ArgumentTypeError(f"must be an integer from 0 to {MAX_HEADER_SAMPLE_VALUES}")
    return value


def _cte_type(raw: str) -> str | None:
    """Normalise ``--cte-type`` the way the route normalises its ``cte_type`` form field.

    An empty value means "not declared", as an empty form field does.
    """
    if not raw:
        return None
    canonical = route._CTE_TYPE_ALIASES.get(raw.strip().lower().replace(" ", "_"))
    if not canonical:
        valid = ", ".join(sorted(set(route._CTE_TYPE_ALIASES.values())))
        raise argparse.ArgumentTypeError(f"unknown CTE type '{raw}'; valid: {valid}")
    return canonical


def _parser() -> _Parser:
    parser = _Parser(
        prog=PROG,
        description=(
            "Preview Jev header-mapping suggestions for a local CSV, using the same code path as "
            "POST /api/v1/ingest/csv. Sends the header row only, plus the declared CTE name if --cte-type "
            "is given and no row contradicts it, and redacted samples if asked."
        ),
    )
    parser.add_argument("csv_file", type=Path, help="CSV file to preview")
    parser.add_argument("--json", action="store_true", help="print the machine-readable report")
    parser.add_argument(
        "--sample-values",
        type=_sample_count,
        metavar="N",
        help=f"PII-redacted sample values per unrecognised column (0-{MAX_HEADER_SAMPLE_VALUES}); "
        f"default {HEADER_SAMPLE_VALUES_ENV} or 0",
    )
    parser.add_argument(
        "--simulate-apply",
        action="store_true",
        help=f"compute would_apply as if {APPLY_HEADER_MAPPINGS_ENV}=1",
    )
    parser.add_argument(
        "--prompt-key",
        action="store_true",
        help=f"read the API key from a hidden prompt for this run instead of {API_KEY_ENV}",
    )
    parser.add_argument(
        "--cte-type",
        type=_cte_type,
        metavar="CTE",
        help="the CTE every row of the file records (for example shipping), as the route's cte_type "
        "form field; omit for mixed-type files",
    )
    return parser


def _read_csv_text(path: Path) -> str:
    """Read the file the way the route does: size-capped, then decoded as UTF-8 with an optional BOM."""
    try:
        if not path.is_file():
            raise _UsageError(f"{path}: not a file")
        size = path.stat().st_size
        if size > MAX_CSV_FILE_SIZE_BYTES:
            raise _UsageError(
                f"{path}: {size} bytes exceeds the upload limit of {MAX_CSV_FILE_SIZE_BYTES} bytes "
                "(the route rejects it with 413)"
            )
        content = path.read_bytes()
    except OSError as exc:
        raise _UsageError(f"{path}: {exc.strerror or exc}") from None
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise _UsageError(f"{path}: not UTF-8 text") from None


def _header_row(path: Path, text: str) -> tuple[list[str], str | None]:
    """The header row as the route reads it (same helper) and why it is malformed, or a usage error if none."""
    try:
        headers, _, malformed = route._csv_headers_and_samples(text, 0)
    except csv.Error as exc:
        raise _UsageError(f"{path}: not parseable as CSV ({exc})") from None
    if not headers:
        raise _UsageError(f"{path}: no header row")
    return headers, malformed


def _resolve_settings(
    args: argparse.Namespace, env: Mapping[str, str] | None, read_key: Callable[[str], str]
) -> JevSettings:
    settings = JevSettings.from_env(env)
    overrides: dict[str, Any] = {}
    if args.prompt_key:
        try:
            entered = read_key(KEY_PROMPT)
        except EOFError:
            entered = ""
        overrides["api_key"] = entered.strip() or None
    if args.sample_values is not None:
        overrides["header_sample_values"] = args.sample_values
    if args.simulate_apply:
        overrides["apply_header_mappings"] = True
    return dataclasses.replace(settings, **overrides) if overrides else settings


def _exit_code(status: str) -> int:
    if status in ("ok", "no_unrecognized_headers"):
        return EXIT_OK
    if status == "disabled":
        return EXIT_NOT_CONFIGURED
    if status.startswith("unavailable:"):
        return EXIT_UNAVAILABLE
    return EXIT_USAGE


def _hint(status: str, settings: JevSettings, prompted: bool, malformed: str | None = None) -> str | None:
    if status == MALFORMED_HEADER:
        return (
            f"The header row is malformed ({malformed}), so nothing was sent: "
            "check it for an unterminated quote or a line break inside a header."
        )
    if status == "disabled":
        if not settings.api_key:
            if prompted:
                return "No key was entered at the prompt."
            return f"{API_KEY_ENV} is not set: export it in this shell, or re-run with --prompt-key."
        return f"{ENABLED_ENV} switches Jev off: unset it or set it to 1."
    if status.startswith("unavailable:"):
        return _UNAVAILABLE_HINTS.get(status.split(":", 1)[1], "See the jev.unavailable line above.")
    if status in ("ok", "no_unrecognized_headers"):
        return None
    return "Unexpected error while preparing the request: see the log lines above."


def _build_report(
    path: Path,
    result: HeaderMappingResult,
    settings: JevSettings,
    headers: Sequence[str],
    unknown: Sequence[str],
    *,
    simulated: bool,
    prompted: bool,
    file_cte_type_dropped: str | None = None,
    malformed_header_reason: str | None = None,
) -> dict[str, Any]:
    evidence = result.evidence
    suggestions = []
    for suggestion in result.suggestions:
        item = suggestion.to_dict()
        # A preview applies nothing: ``applied`` here means the route would apply it.
        item["would_apply"] = item.pop("applied")
        suggestions.append(item)
    return {
        "file": str(path),
        "status": result.status,
        "exit_code": _exit_code(result.status),
        "hint": _hint(result.status, settings, prompted, malformed_header_reason),
        "engine": {
            "provider": "typesafe",
            "requested_model": settings.model,
            "model": evidence.model if evidence else None,
            "request_id": evidence.request_id if evidence else None,
            "latency_ms": evidence.latency_ms if evidence else None,
            "questions_version": evidence.questions_version if evidence else None,
            "input_tokens": evidence.input_tokens if evidence else None,
            "output_tokens": evidence.output_tokens if evidence else None,
            "base_url_host": _host(settings.base_url),
        },
        "policy": {
            "auto_apply_confidence": settings.auto_apply_confidence,
            "review_confidence": settings.review_confidence,
            "apply_enabled": settings.apply_header_mappings,
            "simulated_apply": simulated,
        },
        "request": {
            "header_count": len(headers),
            "unrecognized_headers": list(unknown),
            "malformed_header_reason": malformed_header_reason,
            "file_cte_type": result.file_cte_type,
            "file_cte_type_dropped": file_cte_type_dropped,
            "truncated_columns": result.truncated_columns,
            "sample_values_per_column": settings.header_sample_values,
            "rows_sent": 0,
        },
        "suggestions": suggestions,
    }


def _host(url: str | None) -> str | None:
    """Hostname of ``url`` for the report; ``None`` when absent or unparseable."""
    if not url:
        return None
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def _table(rows: Sequence[Sequence[str]]) -> list[str]:
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return lines


def _render_text(report: dict[str, Any]) -> str:
    engine, policy, request = report["engine"], report["policy"], report["request"]
    apply_state = "on" if policy["apply_enabled"] else "off"
    if policy["simulated_apply"]:
        apply_state += f" (simulated: {APPLY_HEADER_MAPPINGS_ENV}=1)"
    lines = [
        f"Jev header-mapping preview: {report['file']}",
        f"Status:  {report['status']}",
    ]
    if engine["model"]:
        lines.append(
            f"Engine:  model {engine['model']} (requested {engine['requested_model']}), "
            f"request id {engine['request_id'] or 'n/a'}, latency {engine['latency_ms']} ms"
        )
    else:
        lines.append(f"Engine:  requested model {engine['requested_model']}, no answer received")
    lines.append(
        f"Policy:  auto_apply >= {policy['auto_apply_confidence']:.2f}, "
        f"review >= {policy['review_confidence']:.2f}, apply to rows: {apply_state}"
    )
    unknown = request["unrecognized_headers"]
    if request["malformed_header_reason"]:
        # Never echo the "headers": they may be whole rows of the file.
        columns = f"Columns: the header row is malformed: {request['malformed_header_reason']}"
    else:
        columns = f"Columns: {request['header_count']} in the header row, {len(unknown)} unrecognised"
    if request["truncated_columns"]:
        columns += f" ({request['truncated_columns']} over the per-upload cap, not asked)"
    lines.append(columns)
    if report["status"] == "ok" or report["status"].startswith("unavailable:"):
        # On an unavailable status the request may never have left (connection
        # refused, SDK-side refusal), so say what was attempted, not what was sent.
        label = "Sent:   " if report["status"] == "ok" else "Attempted:"
        cte = f"file_cte_type {request['file_cte_type']}; " if request["file_cte_type"] else ""
        lines.append(
            f"{label} header row; {cte}{request['sample_values_per_column']} redacted sample value(s) per "
            "unrecognised column; no rows"
        )
    elif report["status"] in ("disabled", "no_unrecognized_headers", MALFORMED_HEADER):
        lines.append("Sent:    nothing")
    if request["file_cte_type_dropped"]:
        verdict = "would be withheld from Jev" if report["status"] == "disabled" else "not sent to Jev"
        lines.append(f"CTE:     --cte-type {verdict}: {request['file_cte_type_dropped']}")
    if unknown and not report["suggestions"]:
        lines.append("Unrecognised: " + ", ".join(unknown))
    if report["suggestions"]:
        rows = [["column", "suggested_field", "confidence", "band", "would_apply", "blocked_reason"]]
        for item in report["suggestions"]:
            blocked = item["blocked_reason"] or "-"
            if item["shadowed_columns"]:
                blocked += f" ({', '.join(item['shadowed_columns'])})"
            rows.append(
                [
                    item["source_header"],
                    item["canonical_field"] or "(no match)",
                    f"{item['confidence']:.3f}",
                    item["band"],
                    "yes" if item["would_apply"] else "no",
                    blocked,
                ]
            )
        lines.append("")
        lines.extend(_table(rows))
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    transport: Any | None = None,
    read_key: Callable[[str], str] = getpass.getpass,
) -> int:
    """Run the preview. ``env``, ``transport`` and ``read_key`` exist for offline tests."""
    try:
        args = _parser().parse_args(argv)
        text = _read_csv_text(args.csv_file)
        headers, malformed = _header_row(args.csv_file, text)
    except _UsageError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    settings = _resolve_settings(args, env, read_key)
    unknown: list[str] = []
    dropped: str | None = None
    if malformed:
        # The route's own check (_csv_headers_and_samples) says the "headers"
        # may be row data. The route sends nothing for such a file; the
        # preview sends nothing either, with or without a key.
        result = HeaderMappingResult(
            status=MALFORMED_HEADER, thresholds=settings.thresholds, apply_enabled=settings.apply_header_mappings
        )
    else:
        decider = JevDecider(settings, transport=transport)
        try:
            result = asyncio.run(
                route._suggest_header_mappings_for_upload(text, decider=decider, cte_type=args.cte_type)
            )
        finally:
            decider.close()
        unknown = unrecognized_headers(headers, route._RECOGNIZED_COLUMNS)
        # What the route's own helper withheld, and why. Without Jev configured
        # it returns before looking at the file, so ask the same rule directly:
        # the operator still learns that --cte-type would be withheld. Nothing
        # was sent, so request.file_cte_type stays null.
        dropped = result.file_cte_type_dropped
        if dropped is None and result.status == "disabled":
            _, dropped = route._file_cte_type_for_jev(text, args.cte_type)
    report = _build_report(
        args.csv_file,
        result,
        settings,
        headers,
        unknown,
        simulated=args.simulate_apply,
        prompted=args.prompt_key,
        file_cte_type_dropped=dropped,
        malformed_header_reason=malformed,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_render_text(report))
    if report["exit_code"] != EXIT_OK:
        print(f"{PROG}: {report['status']}: {report['hint']}", file=sys.stderr)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
