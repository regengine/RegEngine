#!/usr/bin/env python3
"""Ask TypeSafe Jev typed questions from the command line.

A sidecar for people and coding agents working in this repo: when a request
involves a judgment Jev can make (which of these, is this true, how much), ask
Jev next to your own reasoning and report its answer with its confidence.

    python3 scripts/jev_ask.py \\
        --state '{"headers": ["Ship Dte", "Cust Name", "Lot No."]}' \\
        --choice cte "Which FSMA 204 CTE do these CSV headers record?" \\
            "shipping=outbound shipments" "receiving=inbound deliveries" "unclear=cannot tell" \\
        --noul has_lot "Do the headers include a lot code column?" \\
        --score risk "How likely is this file to be rejected as-is?" "low" "medium" "high"

    python3 scripts/jev_ask.py --state-file state.json --questions-file questions.json --json

Question kinds (see https://docs.typesafe.ai/primitives.md):
    --choice ID TEXT OPTION [OPTION ...]   pick one; OPTION is ``name`` or ``name=description``
    --noul ID TEXT                         yes/no question; the answer is p(yes)
    --score ID TEXT LEVEL LEVEL [...]      position on 2-10 ordered levels, lowest first
    --questions-file FILE                  questions as the API takes them (a JSON object)

State is what Jev judges: ``--state`` (a JSON value, or plain text when it is
not JSON), ``--state-file``, or stdin with ``--state-file -``. Send only what the
question needs. Never send credentials, secrets, customer row data or personal
data: the state leaves this machine for api.typesafe.ai.

The key comes from ``TYPESAFE_API_KEY`` or, with ``--prompt-key``, a hidden
prompt for this run. It is never printed, logged or written.

Run it with ``venv/bin/python`` in a Claude Code session (the session start hook
installs ``requirements.lock`` there); plain ``python3`` works wherever the
repo's requirements are installed.

Exit codes: 0 answered; 1 bad usage; 2 not configured (no key, switched off, or
packages missing), nothing sent; 3 Jev unavailable.
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
PROG = "jev_ask"
PURPOSE = "agent_sidecar"
KEY_PROMPT = "TypeSafe API key (hidden when typed at a terminal): "

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
    """Warnings and above to stderr with plain tracebacks, so stdout carries only the answer."""
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
    from shared.jev import JevDecider, JevSettings, JevUnavailable
    from shared.jev.settings import API_KEY_ENV, ENABLED_ENV
except ImportError as exc:
    _missing_dependency(exc)


class _UsageError(Exception):
    """Bad arguments: exit 1."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)


def _parser() -> _Parser:
    parser = _Parser(prog=PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--state", help="the state: a JSON value, or plain text when it is not JSON")
    source.add_argument("--state-file", help="read the state from a file (JSON or text); '-' reads stdin")
    parser.add_argument("--choice", nargs="+", action="append", default=[], metavar="ARG", help="ID TEXT OPTION...")
    parser.add_argument(
        "--noul",
        nargs=2,
        action="append",
        default=[],
        metavar=("ID", "TEXT"),
        help="yes/no question; the answer is p(yes)",
    )
    parser.add_argument("--score", nargs="+", action="append", default=[], metavar="ARG", help="ID TEXT LEVEL...")
    parser.add_argument("--questions-file", help="questions as a JSON object in the API's format")
    parser.add_argument("--json", action="store_true", help="print the machine-readable answers")
    parser.add_argument(
        "--prompt-key",
        action="store_true",
        help=f"read the API key from a hidden prompt for this run instead of {API_KEY_ENV}",
    )
    return parser


def _parse_state(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _read_state(args: argparse.Namespace, stdin: Any) -> Any:
    if args.state is not None:
        return _parse_state(args.state)
    if args.state_file == "-":
        return _parse_state(stdin.read())
    try:
        return _parse_state(Path(args.state_file).read_text(encoding="utf-8"))
    except OSError as exc:
        raise _UsageError(f"{args.state_file}: {exc.strerror or exc}") from None


def _option(raw: str) -> tuple[str, str | None]:
    name, sep, description = raw.partition("=")
    name = name.strip()
    if not name:
        raise _UsageError(f"empty option name in {raw!r}")
    return name, (description.strip() or None) if sep else None


def build_questions(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    """Turn the command line into the API's question object, keyed by question id."""
    questions: dict[str, dict[str, Any]] = {}

    def add(question_id: str, question: dict[str, Any]) -> None:
        if question_id in questions:
            raise _UsageError(f"duplicate question id {question_id!r}")
        questions[question_id] = question

    for spec in args.choice:
        if len(spec) < 4:
            raise _UsageError("--choice needs ID TEXT and at least two OPTIONs")
        question_id, text, *raw_options = spec
        options = dict(_option(raw) for raw in raw_options)
        if len(options) != len(raw_options):
            raise _UsageError(f"--choice {question_id}: option names must be distinct")
        add(question_id, {"type": "choice", "instructions": text, "criteria": options})
    for question_id, text in args.noul:
        add(question_id, {"type": "noul", "instructions": text})
    for spec in args.score:
        if not 4 <= len(spec) <= 12:
            raise _UsageError("--score needs ID TEXT and 2 to 10 LEVELs, lowest first")
        question_id, text, *levels = spec
        add(question_id, {"type": "score", "instructions": text, "criteria": levels})
    if args.questions_file:
        try:
            loaded = json.loads(Path(args.questions_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise _UsageError(f"{args.questions_file}: {exc}") from None
        if not isinstance(loaded, dict) or not all(isinstance(q, dict) for q in loaded.values()):
            raise _UsageError(f"{args.questions_file}: expected an object of question objects")
        for question_id, question in loaded.items():
            add(question_id, question)
    if not questions:
        raise _UsageError("ask at least one question (--choice, --noul, --score or --questions-file)")
    return questions


def answers_report(answers: Any, questions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The answers as plain data, in the order the questions were asked."""
    report: dict[str, Any] = {
        "model": answers.evidence.model,
        "request_id": answers.evidence.request_id,
        "latency_ms": answers.evidence.latency_ms,
        "answers": {},
    }
    for question_id, question in questions.items():
        kind = question.get("type")
        if question_id in answers.choices:
            result = answers.choices[question_id]
            report["answers"][question_id] = {
                "type": "choice",
                "choice": result.choice,
                "confidence": result.confidence,
                "probabilities": result.probabilities,
            }
        elif question_id in answers.nouls:
            report["answers"][question_id] = {"type": "noul", "probability_yes": answers.nouls[question_id].probability}
        elif question_id in answers.scores:
            result = answers.scores[question_id]
            report["answers"][question_id] = {
                "type": "score",
                "score": result.score,
                "confidence": result.confidence,
                "probabilities": {str(k): v for k, v in result.probabilities.items()},
                "legend": {str(k): v for k, v in result.legend.items()},
            }
        else:
            report["answers"][question_id] = {"type": kind, "missing": True}
    return report


def render_text(report: Mapping[str, Any]) -> str:
    lines = [f"Jev ({report['model']}, request {report['request_id'] or 'n/a'}, {report['latency_ms']} ms)"]
    for question_id, answer in report["answers"].items():
        if answer.get("missing"):
            lines.append(f"  {question_id}: no answer in the response")
        elif answer["type"] == "choice":
            ranked = sorted(answer["probabilities"].items(), key=lambda item: -item[1])[:3]
            spread = ", ".join(f"{name} {p:.2f}" for name, p in ranked)
            lines.append(
                f"  {question_id} [choice]: {answer['choice']} (confidence {answer['confidence']:.2f}; {spread})"
            )
        elif answer["type"] == "noul":
            p_yes = answer["probability_yes"]
            verdict = "yes" if p_yes >= 0.5 else "no"
            lines.append(f"  {question_id} [noul]: {verdict} (p(yes)={p_yes:.2f})")
        else:
            legend = answer["legend"]
            nearest = legend.get(str(round(answer["score"])), "")
            lines.append(
                f"  {question_id} [score]: {answer['score']:.2f} on 0..{len(legend) - 1}"
                f"{f' ~ {nearest}' if nearest else ''} (confidence {answer['confidence']:.2f})"
            )
    return "\n".join(lines)


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    transport: Any | None = None,
    read_key: Callable[[str], str] = getpass.getpass,
    stdin: Any = None,
) -> int:
    """Ask once and print. ``env``, ``transport``, ``read_key`` and ``stdin`` exist for offline tests."""
    try:
        args = _parser().parse_args(argv)
        questions = build_questions(args)
        state = _read_state(args, stdin if stdin is not None else sys.stdin)
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
    if not settings.enabled:
        reason = f"{API_KEY_ENV} is not set" if not settings.api_key else f"{ENABLED_ENV} switches Jev off"
        print(f"{PROG}: not configured: {reason}. Nothing was sent.", file=sys.stderr)
        return EXIT_NOT_CONFIGURED

    decider = JevDecider(settings, transport=transport)
    try:
        answers = decider.ask(state, questions, purpose=PURPOSE, questions_version="adhoc")
    except JevUnavailable as exc:
        print(f"{PROG}: unavailable: {exc.reason}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    finally:
        decider.close()
    report = answers_report(answers, questions)
    print(json.dumps(report, indent=2) if args.json else render_text(report))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
