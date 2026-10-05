#!/usr/bin/env python3
"""Extract structured data from a local document with LlamaIndex Extract v2.5.

Runs the code the bulk-upload PDF path runs
(``shared.document_extract.DocumentExtractor``): the same upload, the same
tier/version pins, the same evidence. Nothing is ingested, persisted or
queued, and no database is used.

    python3 scripts/extract_document.py supplier_packet.pdf                 # FSMA 204 supplier schema
    python3 scripts/extract_document.py supplier_packet.pdf --json          # machine-readable report
    python3 scripts/extract_document.py invoice.pdf --schema invoice.json   # any JSON Schema
    python3 scripts/extract_document.py scan.png --tier agentic_plus --target per_page
    python3 scripts/extract_document.py packet.pdf --rows                   # bulk-upload parser rows
    python3 scripts/extract_document.py packet.pdf --prompt-key

Configuration comes from the environment through
``shared.document_extract.DocumentExtractSettings`` (``LLAMA_CLOUD_API_KEY``,
``LLAMA_CLOUD_BASE_URL`` and the ``REGENGINE_DOC_EXTRACT_*`` variables; see
docs/engineering/DOCUMENT_EXTRACT.md). ``--tier``, ``--version`` and
``--max-pages`` override the environment for this run. ``--prompt-key`` reads
the key with ``getpass`` instead (hidden on a terminal; read from stdin
otherwise), for this run only. The script never prints, logs or writes the key.

What leaves the process is the whole document, as in production. Do not run
this on a tenant's document outside that tenant's engagement.

Exit codes:
    0  extraction received
    1  bad usage; unreadable, oversized or unsupported file; invalid schema file; unexpected error
    2  Extract not configured (no LLAMA_CLOUD_API_KEY) or switched off (REGENGINE_DOC_EXTRACT_ENABLED)
    3  Extract unavailable (auth, rate limit, timeout, job failure, server error, ...)
"""

from __future__ import annotations

import argparse
import dataclasses
import getpass
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
for entry in (REPO_ROOT, REPO_ROOT / "services"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from shared.document_extract import (  # noqa: E402
    EXTRACTION_TARGETS,
    SUPPLIER_DOCUMENT_SCHEMA,
    SUPPLIER_SCHEMA_VERSION,
    TIERS,
    DocumentExtractor,
    DocumentExtractSettings,
    DocumentExtractUnavailable,
    rows_from_extraction,
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_CONFIGURED = 2
EXIT_UNAVAILABLE = 3

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
SUPPORTED_SUFFIXES = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".webp",
    ".docx",
    ".doc",
    ".pptx",
    ".xlsx",
    ".xls",
    ".csv",
    ".txt",
    ".html",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("document", type=Path, help="Local document to extract from")
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="JSON Schema file to extract against (default: the FSMA 204 supplier schema)",
    )
    parser.add_argument("--tier", choices=TIERS, default=None, help="Extract tier for this run")
    parser.add_argument("--version", dest="extract_version", default=None, help="Extract release: YYYY-MM-DD or latest")
    parser.add_argument("--target", choices=EXTRACTION_TARGETS, default="per_doc", help="Extraction granularity")
    parser.add_argument("--max-pages", type=int, default=None, help="Pages to send (capped by the environment's limit)")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Refuse files larger than this")
    parser.add_argument("--system-prompt", default=None, help="Extra guidance for the extraction agent")
    parser.add_argument(
        "--rows", action="store_true", help="Also print the bulk-upload parser rows (supplier schema only)"
    )
    parser.add_argument("--json", action="store_true", help="Print one JSON report instead of text")
    parser.add_argument("--prompt-key", action="store_true", help="Read LLAMA_CLOUD_API_KEY interactively for this run")
    parser.add_argument(
        "--verbose", action="store_true", help="Show the wrapper's own log lines (never the key or data)"
    )
    return parser


def _read_document(path: Path, max_bytes: int) -> bytes:
    if not path.is_file():
        raise SystemExit(f"error: {path} is not a file")
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise SystemExit(
            f"error: unsupported file type {path.suffix!r}; supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    size = path.stat().st_size
    if size == 0:
        raise SystemExit(f"error: {path} is empty")
    if size > max_bytes:
        raise SystemExit(f"error: {path} is {size} bytes; --max-bytes is {max_bytes}")
    return path.read_bytes()


def _read_schema(path: Path | None) -> tuple[dict[str, Any], str]:
    if path is None:
        return SUPPLIER_DOCUMENT_SCHEMA, f"supplier:{SUPPLIER_SCHEMA_VERSION}"
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"error: cannot read schema {path}: {exc}") from exc
    if not isinstance(schema, dict) or schema.get("type", "object") != "object":
        raise SystemExit(f"error: schema {path} must be a JSON object schema")
    return schema, f"file:{path.name}"


def _settings(args: argparse.Namespace) -> DocumentExtractSettings:
    settings = DocumentExtractSettings.from_env()
    overrides: dict[str, Any] = {}
    if args.prompt_key:
        key = getpass.getpass("LLAMA_CLOUD_API_KEY: ") if sys.stdin.isatty() else sys.stdin.readline().strip()
        if not key:
            raise SystemExit("error: no key entered")
        overrides["api_key"] = key
    if args.tier:
        overrides["tier"] = args.tier
    if args.extract_version:
        overrides["version"] = args.extract_version
    if overrides:
        settings = dataclasses.replace(settings, **overrides)
    return settings


def _print_text(result_dict: dict[str, Any], rows: list[dict[str, Any]] | None, path: Path) -> None:
    evidence = result_dict["evidence"]
    confidence = result_dict["confidence"]
    print(f"Extracted: {path.name}")
    print(
        f"  job={evidence['job_id']} tier={evidence['tier'] or evidence['requested_tier']} "
        f"version={evidence['version'] or evidence['requested_version']} target={evidence['extraction_target']}"
    )
    print(
        f"  pages_extracted={evidence['pages_extracted']} pages_billed={evidence['pages_billed']} "
        f"credits={evidence['credits']} latency_ms={evidence['latency_ms']}"
    )
    print(f"  confidence: fields={confidence['fields']} min={confidence['min']} mean={confidence['mean']}")
    print()
    print(json.dumps(result_dict["data"], indent=2, ensure_ascii=False))
    if rows is not None:
        print()
        print(f"Bulk-upload parser rows ({len(rows)}):")
        for row in rows:
            print("  " + json.dumps(row, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")

    try:
        content = _read_document(args.document, args.max_bytes)
        schema, schema_version = _read_schema(args.schema)
        settings = _settings(args)
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return EXIT_USAGE
        raise

    if not settings.enabled:
        summary = settings.public_summary()
        if summary["kill_switch"]:
            print("Extract is switched off (REGENGINE_DOC_EXTRACT_ENABLED).", file=sys.stderr)
        else:
            print("Extract is not configured: set LLAMA_CLOUD_API_KEY or pass --prompt-key.", file=sys.stderr)
        return EXIT_NOT_CONFIGURED

    extractor = DocumentExtractor(settings)
    try:
        result = extractor.extract(
            content,
            filename=args.document.name,
            data_schema=schema,
            purpose="extract_document_cli",
            schema_version=schema_version,
            extraction_target=args.target,
            max_pages=args.max_pages,
            system_prompt=args.system_prompt,
        )
    except DocumentExtractUnavailable as exc:
        print(f"Extract unavailable: {exc.reason}" + (f" (status={exc.status})" if exc.status else ""), file=sys.stderr)
        return EXIT_UNAVAILABLE
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    finally:
        extractor.close()

    rows = rows_from_extraction(result.data) if (args.rows and args.schema is None) else None
    report = result.to_dict()
    if rows is not None:
        report["rows"] = rows

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    else:
        _print_text(report, rows, args.document)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
