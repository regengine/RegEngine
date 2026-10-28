#!/usr/bin/env python3
"""Measure TypeSafe Jev on RegEngine's own CSV header rows.

The confidence thresholds in ``shared.jev`` are the vendor's published
starting points. This script checks them against labelled RegEngine data
before any apply switch is turned on: it asks the two questions
``POST /api/v1/ingest/csv`` asks, with the same question sets and policy
code, for every labelled header row, and scores the answers.

    python3 scripts/jev_eval.py --prompt-key
    python3 scripts/jev_eval.py --json > jev-eval.json
    python3 scripts/jev_eval.py --cases my_cases.json --no-templates

The cases are RegEngine's seven CSV templates (built from ``CTE_COLUMNS``,
labelled with their CTE) plus ``docs/engineering/examples/jev_eval_cases.json``:
supplier-style header rows with the acceptable CTE and the acceptable
canonical field for each unrecognised column.

What leaves the process: header rows only. The cases hold no row values, and
sample values are never sent. The key comes from ``TYPESAFE_API_KEY`` or, with
``--prompt-key``, a hidden prompt; it is never printed, logged or written.

For each question set the report gives accuracy, and for a sweep of
thresholds the precision of the answers that would be applied (right or
wrong) and their coverage. The recommended auto-apply threshold is the
lowest swept value, not below the agent-artifact review floor (0.85), at
which no applied answer was wrong. It is a floor to start from on this
data, not a guarantee: a small labelled set can only show errors, never
their absence.

Exit codes:
    0  every case answered (some may be wrong: read the report)
    1  bad usage or an invalid cases file
    2  Jev not configured (no TYPESAFE_API_KEY) or switched off (REGENGINE_JEV_ENABLED)
    3  Jev unavailable for at least one request
"""

from __future__ import annotations

import argparse
import dataclasses
import getpass
import json
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import structlog

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "services" / "ingestion", ROOT / "services"):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

DEFAULT_CASES = ROOT / "docs" / "engineering" / "examples" / "jev_eval_cases.json"
_IRRELEVANT_IMPORT_NOTICES = frozenset({"database_url_default", "rate_limit_redis_not_configured"})


def _drop_irrelevant_import_notices(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if event_dict.get("event") in _IRRELEVANT_IMPORT_NOTICES:
        raise structlog.DropEvent
    return event_dict


def _configure_cli_logging() -> None:
    """Warnings and above to stderr, plain tracebacks (no locals), stdout left for the report."""
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
from shared.agent_artifacts import HUMAN_REVIEW_CONFIDENCE_THRESHOLD  # noqa: E402
from shared.jev import JevDecider, JevSettings  # noqa: E402
from shared.jev.cte_classification import CTE_NAMES, MIXED_OR_UNCLEAR, suggest_file_cte_type  # noqa: E402
from shared.jev.header_mapping import (  # noqa: E402
    CANONICAL_FIELD_NAMES,
    NO_MATCH,
    suggest_header_mappings,
    unrecognized_headers,
)

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_CONFIGURED = 2
EXIT_UNAVAILABLE = 3
PROG = "jev_eval"
KEY_PROMPT = "TypeSafe API key (hidden when typed at a terminal): "
SWEEP = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98)
CTE_LABELS = CTE_NAMES | {MIXED_OR_UNCLEAR}
FIELD_LABELS = CANONICAL_FIELD_NAMES | {NO_MATCH}


class _UsageError(Exception):
    """Bad arguments or an invalid cases file: exit 1."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)


@dataclasses.dataclass(frozen=True)
class Case:
    id: str
    headers: tuple[str, ...]
    cte: frozenset[str] | None
    mappings: Mapping[str, frozenset[str]]


@dataclasses.dataclass(frozen=True)
class Scored:
    """One answer against its label. ``answer`` is a CTE or field name, or the no-answer label."""

    case_id: str
    subject: str
    expected: tuple[str, ...]
    answer: str | None
    confidence: float | None
    band: str | None
    correct: bool
    status: str

    @property
    def acts(self) -> bool:
        """Whether the answer names something (a CTE or a field) rather than declining."""
        return self.answer is not None and self.answer not in (MIXED_OR_UNCLEAR, NO_MATCH)


def _labels(value: Any, allowed: frozenset[str], where: str) -> frozenset[str]:
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not names or not all(isinstance(name, str) for name in names):
        raise _UsageError(f"{where}: a label is a name or a non-empty list of names")
    unknown = sorted(set(names) - allowed)
    if unknown:
        raise _UsageError(f"{where}: unknown label(s) {', '.join(unknown)}")
    return frozenset(names)


def load_cases(path: Path, *, templates: bool) -> list[Case]:
    """The template cases (when asked) followed by the file's cases, validated."""
    cases: list[Case] = []
    if templates:
        for cte, columns in route.CTE_COLUMNS.items():
            if cte in CTE_NAMES:
                cases.append(Case(f"template-{cte}", tuple(c[0] for c in columns), frozenset({cte}), {}))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _UsageError(f"{path}: {exc.strerror or exc}") from None
    except json.JSONDecodeError as exc:
        raise _UsageError(f"{path}: not JSON ({exc})") from None
    raw_cases = data.get("cases") if isinstance(data, dict) else None
    if not isinstance(raw_cases, list):
        raise _UsageError(f"{path}: expected an object with a 'cases' list")
    seen: set[str] = {case.id for case in cases}
    for index, raw in enumerate(raw_cases):
        where = f"{path.name} case {index}"
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"]:
            raise _UsageError(f"{where}: each case needs a string 'id'")
        where = f"{path.name} case {raw['id']!r}"
        if raw["id"] in seen:
            raise _UsageError(f"{where}: duplicate id")
        seen.add(raw["id"])
        headers = raw.get("headers")
        if not isinstance(headers, list) or not headers or not all(isinstance(h, str) for h in headers):
            raise _UsageError(f"{where}: 'headers' must be a non-empty list of strings")
        cte = None if raw.get("cte") is None else _labels(raw["cte"], CTE_LABELS, f"{where} cte")
        mappings_raw = raw.get("mappings") or {}
        if not isinstance(mappings_raw, dict):
            raise _UsageError(f"{where}: 'mappings' must be an object")
        missing = sorted(set(mappings_raw) - set(headers))
        if missing:
            raise _UsageError(f"{where}: mapping labels for headers not in the row: {', '.join(missing)}")
        mappings = {h: _labels(v, FIELD_LABELS, f"{where} mapping {h!r}") for h, v in mappings_raw.items()}
        cases.append(Case(raw["id"], tuple(headers), cte, mappings))
    return cases


def _ask_cte(case: Case, decider: JevDecider) -> Scored | None:
    """The file-CTE question, as the route asks it: never for a row with a per-row CTE column."""
    if case.cte is None or route._per_row_cte_column(case.headers) is not None:
        return None
    result = suggest_file_cte_type(case.headers, decider=decider)
    suggestion = result.suggestion
    answer = None
    if suggestion is not None:
        answer = suggestion.cte_type or MIXED_OR_UNCLEAR
    return Scored(
        case_id=case.id,
        subject="(file)",
        expected=tuple(sorted(case.cte)),
        answer=answer,
        confidence=suggestion.confidence if suggestion else None,
        band=suggestion.band.value if suggestion else None,
        correct=answer in case.cte if answer is not None else False,
        status=result.status,
    )


def _ask_mappings(case: Case, decider: JevDecider) -> list[Scored]:
    if not case.mappings:
        return []
    result = suggest_header_mappings(
        case.headers, recognized=route._RECOGNIZED_COLUMNS, decider=decider, precedence=route._COLUMN_PRECEDENCE
    )
    by_header = {s.source_header: s for s in result.suggestions}
    scored = []
    for header, expected in case.mappings.items():
        suggestion = by_header.get(header)
        answer = None
        if suggestion is not None:
            answer = suggestion.canonical_field or NO_MATCH
        scored.append(
            Scored(
                case_id=case.id,
                subject=header,
                expected=tuple(sorted(expected)),
                answer=answer,
                confidence=suggestion.confidence if suggestion else None,
                band=suggestion.band.value if suggestion else None,
                correct=answer in expected if answer is not None else False,
                status=result.status,
            )
        )
    return scored


def recognized_labels(cases: Sequence[Case]) -> list[str]:
    """Labelled headers the parser already reads: never asked, so never scored. Fix the cases file."""
    found = []
    for case in cases:
        asked = set(unrecognized_headers(case.headers, route._RECOGNIZED_COLUMNS))
        found.extend(f"{case.id}: {header}" for header in case.mappings if header.strip() not in asked)
    return found


def summarize(scored: Sequence[Scored], *, current_threshold: float) -> dict[str, Any]:
    """Accuracy, the threshold sweep and the recommendation for one question set."""
    answered = [s for s in scored if s.answer is not None and s.confidence is not None]
    # Coverage counts the subjects whose label allows applying something.
    applicable = [s for s in scored if any(e not in (MIXED_OR_UNCLEAR, NO_MATCH) for e in s.expected)]
    sweep = []
    for threshold in sorted({*SWEEP, current_threshold}):
        applied = [s for s in answered if s.acts and s.confidence >= threshold]
        wrong = [s for s in applied if not s.correct]
        sweep.append(
            {
                "threshold": threshold,
                "applied": len(applied),
                "wrong": len(wrong),
                "precision": round(1 - len(wrong) / len(applied), 4) if applied else None,
                "coverage": round(len(applied) / len(applicable), 4) if applicable else None,
            }
        )
    floor = HUMAN_REVIEW_CONFIDENCE_THRESHOLD
    safe = [row for row in sweep if row["threshold"] >= floor and row["applied"] and not row["wrong"]]
    correct = [s for s in answered if s.correct]
    incorrect = [s for s in answered if not s.correct]
    return {
        "asked": len(scored),
        "answered": len(answered),
        "correct": len(correct),
        "accuracy": round(len(correct) / len(answered), 4) if answered else None,
        "mean_confidence_correct": round(sum(s.confidence for s in correct) / len(correct), 4) if correct else None,
        "mean_confidence_wrong": round(sum(s.confidence for s in incorrect) / len(incorrect), 4) if incorrect else None,
        "sweep": sweep,
        "recommended_auto_apply": safe[0]["threshold"] if safe else None,
        "wrong_at_current_threshold": [
            {"case": s.case_id, "subject": s.subject, "answer": s.answer, "expected": list(s.expected)}
            for s in answered
            if s.acts and not s.correct and s.confidence >= current_threshold
        ],
    }


def evaluate(cases: Sequence[Case], decider: JevDecider, *, workers: int = 4) -> tuple[list[Scored], list[Scored]]:
    """Ask both questions for every case, a few requests at a time."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        cte_futures = [pool.submit(_ask_cte, case, decider) for case in cases]
        mapping_futures = [pool.submit(_ask_mappings, case, decider) for case in cases]
        cte = [s for s in (f.result() for f in cte_futures) if s is not None]
        mappings = [s for f in mapping_futures for s in f.result()]
    return cte, mappings


def _status_exit_code(statuses: Sequence[str]) -> int:
    if any(status == "disabled" for status in statuses):
        return EXIT_NOT_CONFIGURED
    if any(status.startswith("unavailable:") for status in statuses):
        return EXIT_UNAVAILABLE
    if any(status not in ("ok", "no_unrecognized_headers") for status in statuses):
        return EXIT_USAGE
    return EXIT_OK


def build_report(
    cases: Sequence[Case],
    cte: Sequence[Scored],
    mappings: Sequence[Scored],
    settings: JevSettings,
) -> dict[str, Any]:
    statuses = [s.status for s in cte] + [s.status for s in mappings]
    return {
        "exit_code": _status_exit_code(statuses),
        "model": settings.model,
        "auto_apply_confidence": settings.auto_apply_confidence,
        "review_confidence": settings.review_confidence,
        "artifact_review_floor": HUMAN_REVIEW_CONFIDENCE_THRESHOLD,
        "cases": len(cases),
        "labelled_but_recognized": recognized_labels(cases),
        "file_cte": summarize(cte, current_threshold=settings.auto_apply_confidence),
        "header_mapping": summarize(mappings, current_threshold=settings.auto_apply_confidence),
        "answers": [dataclasses.asdict(s) | {"kind": "file_cte"} for s in cte]
        + [dataclasses.asdict(s) | {"kind": "header_mapping"} for s in mappings],
    }


def _fmt(value: float | None, pattern: str = "{:.3f}") -> str:
    return "-" if value is None else pattern.format(value)


def render_text(report: dict[str, Any]) -> str:
    lines = [
        f"Jev evaluation: {report['cases']} cases, model {report['model']}",
        f"Current policy: auto_apply >= {report['auto_apply_confidence']:.2f}, "
        f"review >= {report['review_confidence']:.2f}, artifact floor {report['artifact_review_floor']:.2f}",
    ]
    for key, title in (("file_cte", "File CTE"), ("header_mapping", "Header mapping")):
        summary = report[key]
        lines += [
            "",
            f"{title}: {summary['correct']}/{summary['answered']} correct "
            f"(accuracy {_fmt(summary['accuracy'], '{:.1%}')}), {summary['asked'] - summary['answered']} unanswered",
            f"  mean confidence: correct {_fmt(summary['mean_confidence_correct'])}, "
            f"wrong {_fmt(summary['mean_confidence_wrong'])}",
            "  threshold  applied  wrong  precision  coverage",
        ]
        for row in summary["sweep"]:
            lines.append(
                f"  {row['threshold']:>9.2f}  {row['applied']:>7}  {row['wrong']:>5}  "
                f"{_fmt(row['precision'], '{:.1%}'):>9}  {_fmt(row['coverage'], '{:.1%}'):>8}"
            )
        recommended = summary["recommended_auto_apply"]
        lines.append(
            f"  recommended auto-apply threshold: {recommended:.2f}"
            if recommended is not None
            else "  recommended auto-apply threshold: none on this data (keep apply off)"
        )
        for wrong in summary["wrong_at_current_threshold"]:
            lines.append(
                f"  WRONG at current threshold: {wrong['case']} {wrong['subject']}: "
                f"{wrong['answer']} (expected {' or '.join(wrong['expected'])})"
            )
    if report["labelled_but_recognized"]:
        lines += ["", "Labelled headers the parser already reads (never asked; fix the cases file):"]
        lines += [f"  {item}" for item in report["labelled_but_recognized"]]
    return "\n".join(lines)


def _parser() -> _Parser:
    parser = _Parser(
        prog=PROG,
        description="Score Jev's CTE and header-mapping answers on labelled RegEngine header rows. Sends headers only.",
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="labelled cases file (JSON)")
    parser.add_argument("--no-templates", action="store_true", help="skip RegEngine's seven template cases")
    parser.add_argument("--json", action="store_true", help="print the machine-readable report")
    parser.add_argument(
        "--prompt-key",
        action="store_true",
        help="read the API key from a hidden prompt for this run instead of TYPESAFE_API_KEY",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    transport: Any | None = None,
    read_key: Callable[[str], str] = getpass.getpass,
) -> int:
    """Run the evaluation. ``env``, ``transport`` and ``read_key`` exist for offline tests."""
    try:
        args = _parser().parse_args(argv)
        cases = load_cases(args.cases, templates=not args.no_templates)
    except _UsageError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    settings = JevSettings.from_env(env)
    if args.prompt_key:
        try:
            entered = read_key(KEY_PROMPT)
        except EOFError:
            entered = ""
        settings = dataclasses.replace(settings, api_key=entered.strip() or None)
    # Header rows only: the cases hold no row values to sample.
    settings = dataclasses.replace(settings, header_sample_values=0)
    if not settings.enabled:
        # Constant-only messages: never interpolate API_KEY_ENV/api_key (CodeQL clear-text-logging).
        if not settings.api_key:
            print(f"{PROG}: not configured: TYPESAFE_API_KEY is not set. Nothing was sent.", file=sys.stderr)
        else:
            print(
                f"{PROG}: not configured: REGENGINE_JEV_ENABLED switches Jev off. Nothing was sent.",
                file=sys.stderr,
            )
        return EXIT_NOT_CONFIGURED

    decider = JevDecider(settings, transport=transport)
    try:
        cte, mappings = evaluate(cases, decider)
    finally:
        decider.close()
    report = build_report(cases, cte, mappings, settings)
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    if report["exit_code"] != EXIT_OK:
        print(f"{PROG}: some requests failed; see the answers with a status other than ok", file=sys.stderr)
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
