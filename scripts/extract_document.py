#!/usr/bin/env python3
"""Extract structured data from a document with LlamaCloud Extract v2.5.

A sidecar for people and coding agents working in this repo: give it a
document (PDF, image, scan, DOCX, XLSX, CSV) and a JSON Schema, get back JSON
that conforms to the schema, with a citation and confidence per field.

    python3 scripts/extract_document.py --file invoice.pdf --schema schema.json
    python3 scripts/extract_document.py --file bol.pdf --schema-inline \\
        '{"type":"object","properties":{"lot_code":{"type":"string"},"ship_date":{"type":"string"}}}' \\
        --tier agentic_plus --pages 1-2 --json --out bol.json

Options:
    --file PATH            the document to extract from (required)
    --schema PATH          JSON Schema file describing the fields to extract
    --schema-inline JSON   the same schema given inline
    --tier TIER            cost_effective | agentic (default) | agentic_plus | turbo
    --version VERSION      Extract release (default 2.5; "latest" floats)
    --target TARGET        per_doc (default) | per_page | per_table_row
    --pages RANGES         1-based pages to process, e.g. "1,3,5-7"
    --max-pages N          page cap for this run
    --system-prompt TEXT   extra extraction instructions
    --spreadsheet          read cells directly from a workbook (agentic_plus only)
    --json                 print data, field metadata and evidence as one JSON object
    --out PATH             also write that JSON object to a file

The document leaves this machine for LlamaCloud. Send only files you are
authorised to share with the vendor; never credentials or data outside the
tenant the extraction is for.

The key comes from ``LLAMA_CLOUD_API_KEY`` or, with ``--prompt-key``, a hidden
prompt for this run. It is never printed, logged or written.

Run it with ``venv/bin/python`` in a Claude Code session (the session start hook
installs ``requirements.lock`` there); plain ``python3`` works wherever the
repo's requirements are installed.

Exit codes: 0 extracted; 1 bad usage; 2 not configured (no key, switched off, or
packages missing), nothing sent; 3 Extract unavailable (vendor error, failed job).
"""

from __future__ import annotations

import argparse
import dataclasses
import getpass
import json
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_CONFIGURED = 2
EXIT_UNAVAILABLE = 3
PROG = "extract_document"
PURPOSE = "cli"
KEY_PROMPT = "LlamaCloud API key (hidden when typed at a terminal): "

ROOT = Path(__file__).resolve().parents[1]
_services = str(ROOT / "services")
if _services not in sys.path:
    sys.path.insert(0, _services)


def _missing_dependency(exc: ImportError) -> NoReturn:
    """Run as a script without the repo's packages: say how to run it instead of a traceback."""
    if __name__ != "__main__":
        raise exc
    print(
        f"{PROG}: not configured: Python package {exc.name or exc} is not installed. Nothing was sent. "
        "Run it with venv/bin/python (the session start hook installs requirements.lock there) "
        "or install requirements.lock first.",
        file=sys.stderr,
    )
    sys.exit(EXIT_NOT_CONFIGURED)


try:
    import structlog
except ImportError as exc:
    _missing_dependency(exc)


def _configure_cli_logging() -> None:
    """Warnings and above to stderr with plain tracebacks, so stdout carries only the result."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False, exception_formatter=structlog.dev.plain_traceback),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )


if __name__ == "__main__":  # before the imports below can log anything
    _configure_cli_logging()

try:
    from shared.llama_extract import DocumentExtractor, LlamaExtractSettings, LlamaExtractUnavailable
    from shared.llama_extract.client import EXTRACTION_TARGETS
    from shared.llama_extract.settings import API_KEY_ENV, ENABLED_ENV, TIERS
except ImportError as exc:
    _missing_dependency(exc)


class _UsageError(Exception):
    """Bad arguments: exit 1."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)


def _parser() -> _Parser:
    parser = _Parser(prog=PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", required=True, help="the document to extract from")
    schema = parser.add_mutually_exclusive_group(required=True)
    schema.add_argument("--schema", help="JSON Schema file describing the fields to extract")
    schema.add_argument("--schema-inline", help="the JSON Schema given inline")
    parser.add_argument("--tier", choices=TIERS, help="extract tier (default from settings: agentic)")
    parser.add_argument("--version", help='extract release (default from settings: 2.5; "latest" floats)')
    parser.add_argument("--target", choices=EXTRACTION_TARGETS, default="per_doc", help="extraction granularity")
    parser.add_argument("--pages", help='1-based pages to process, e.g. "1,3,5-7"')
    parser.add_argument("--max-pages", type=int, help="page cap for this run")
    parser.add_argument("--system-prompt", help="extra extraction instructions")
    parser.add_argument("--spreadsheet", action="store_true", help="read cells directly from a workbook")
    parser.add_argument("--json", action="store_true", help="print data, field metadata and evidence as JSON")
    parser.add_argument("--out", help="also write the JSON result to this file")
    parser.add_argument(
        "--prompt-key",
        action="store_true",
        help=f"read the API key from a hidden prompt for this run instead of {API_KEY_ENV}",
    )
    return parser


def _load_schema(args: argparse.Namespace) -> dict[str, Any]:
    if args.schema_inline is not None:
        raw = args.schema_inline
        where = "--schema-inline"
    else:
        try:
            raw = Path(args.schema).read_text(encoding="utf-8")
        except OSError as exc:
            raise _UsageError(f"cannot read --schema {args.schema}: {exc.strerror or exc}") from exc
        where = f"--schema {args.schema}"
    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _UsageError(f"{where} is not valid JSON: {exc.msg} at position {exc.pos}") from exc
    if not isinstance(schema, dict) or not schema:
        raise _UsageError(f"{where} must be a non-empty JSON object (a JSON Schema)")
    return schema


def _check_document(path_text: str) -> Path:
    path = Path(path_text)
    if not path.is_file():
        raise _UsageError(f"--file {path_text} is not a file")
    return path


def render_text(result: Mapping[str, Any]) -> str:
    """Human-readable result: the data, then one evidence line."""
    evidence = result["evidence"]
    lines = [json.dumps(result["data"], indent=2, ensure_ascii=False)]
    lines.append(
        "-- extracted by {provider} {product} tier={tier} version={version} job={job} "
        "pages_billed={pages} latency_ms={latency}".format(
            provider=evidence["provider"],
            product=evidence["product"],
            tier=evidence["tier"],
            version=evidence["resolved_version"] or evidence["requested_version"],
            job=evidence["job_id"],
            pages=evidence["pages_billed"],
            latency=evidence["latency_ms"],
        )
    )
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    http_client: Any | None = None,
    read_key: Callable[[str], str] = getpass.getpass,
) -> int:
    """Extract once and print. ``env``, ``http_client`` and ``read_key`` exist for offline tests."""
    try:
        args = _parser().parse_args(argv)
        document = _check_document(args.file)
        schema = _load_schema(args)
    except _UsageError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    settings = LlamaExtractSettings.from_env(env)
    if args.prompt_key:
        try:
            entered = read_key(KEY_PROMPT)
        except EOFError:
            entered = ""
        settings = dataclasses.replace(settings, api_key=entered.strip() or None)
    if not settings.enabled:
        reason = f"{API_KEY_ENV} is not set" if not settings.api_key else f"{ENABLED_ENV} switches Extract off"
        print(f"{PROG}: not configured: {reason}. Nothing was sent.", file=sys.stderr)
        return EXIT_NOT_CONFIGURED

    extractor = DocumentExtractor(settings, http_client=http_client)
    try:
        result = extractor.extract(
            document,
            data_schema=schema,
            purpose=PURPOSE,
            extraction_target=args.target,
            system_prompt=args.system_prompt,
            target_pages=args.pages,
            max_pages=args.max_pages,
            spreadsheet_mode=args.spreadsheet,
            tier=args.tier,
            version=args.version,
        )
    except LlamaExtractUnavailable as exc:
        detail = f" (status {exc.status})" if exc.status is not None else ""
        print(f"{PROG}: unavailable: {exc.reason}{detail}", file=sys.stderr)
        return EXIT_UNAVAILABLE

    payload = result.to_dict()
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else render_text(payload))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
