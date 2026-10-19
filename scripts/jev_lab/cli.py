"""Command line for Jev Lab. Run ``venv/bin/python scripts/jev_lab --help``.

Commands:
    serve    the local page: sandbox, loop controls, constellation (default)
    loop     run the self-improving loop in the terminal
    score    score the current wording on both splits, propose nothing
    ledger   list the generations recorded so far
    export   print a recorded question set, its diff from production and the promotion checklist
    confirm  check a recorded rewrite against production on rows labelled after the split began
    reset    start the next run from the production wording again (--rotate-split: new split too)

Jev: live with ``TYPESAFE_API_KEY`` (or ``--prompt-key``), or ``--fake`` for
the offline stand-in, which sends nothing anywhere and is labelled as fake
everywhere it answers.

Exit codes: 0 done; 1 bad usage; 2 not configured (no key and no --fake),
nothing sent; 3 Jev unavailable.
"""

from __future__ import annotations

import argparse
import dataclasses
import getpass
import json
import logging
import math
import os
import secrets
import socket
import stat
import sys
import threading
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import structlog

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_CONFIGURED = 2
EXIT_UNAVAILABLE = 3
PROG = "jev_lab"
DEFAULT_PORT = 8204
KEY_PROMPT = "TypeSafe API key (hidden when typed at a terminal): "
_QUIET_EVENTS = frozenset({"database_url_default", "rate_limit_redis_not_configured"})


def _drop_quiet(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if event_dict.get("event") in _QUIET_EVENTS:
        raise structlog.DropEvent
    return event_dict


def configure_logging() -> None:
    """Warnings to stderr, metadata only (the Jev client never logs state)."""
    structlog.configure(
        processors=[
            _drop_quiet,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False, exception_formatter=structlog.dev.plain_traceback),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    logging.getLogger("jev").setLevel(logging.WARNING)


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message)


def _parser() -> _Parser:
    from .ledger import default_home
    from .proposer import BACKENDS, DEFAULT_MODEL

    parser = _Parser(prog=PROG, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    def common(p: argparse.ArgumentParser, *, jev: bool = True) -> None:
        p.add_argument("--home", type=Path, default=default_home(), help="ledger directory (default %(default)s)")
        p.add_argument(
            "--fake",
            action="store_true",
            help="use the offline fake Jev (nothing is sent anywhere) and its separate ledger",
        )
        if jev:
            p.add_argument("--prompt-key", action="store_true", help="read the TypeSafe key from a hidden prompt")
            p.add_argument("--max-jev-requests", type=int, default=400, help="request budget (default %(default)s)")
            p.add_argument("--no-cache", action="store_true", help="re-send requests that were answered before")

    def proposer_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--proposer", choices=BACKENDS, help="Claude backend (default claude-cli; offline with --fake)")
        p.add_argument("--model", default=DEFAULT_MODEL, help="Claude model (default %(default)s)")

    serve = sub.add_parser("serve", help="start the local page")
    common(serve)
    proposer_flags(serve)
    serve.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="port on 127.0.0.1, 0 for any free one (default %(default)s)"
    )
    serve.add_argument("--no-open", action="store_true", help="do not open a browser")

    loop = sub.add_parser("loop", help="run the self-improving loop in the terminal")
    common(loop)
    proposer_flags(loop)
    loop.add_argument("--generations", type=int, default=5)
    loop.add_argument("--margin", type=float, default=0.01, help="held-out Brier gain required (default %(default)s)")
    loop.add_argument("--json", action="store_true")

    score = sub.add_parser("score", help="score the current wording on both splits")
    common(score)
    score.add_argument("--json", action="store_true")

    ledger = sub.add_parser("ledger", help="list recorded generations")
    common(ledger, jev=False)
    ledger.add_argument("--json", action="store_true")

    export = sub.add_parser("export", help="print a recorded question set and its diff from production")
    common(export, jev=False)
    export.add_argument("digest", help="question-set digest (see `ledger`), or 'incumbent'")

    confirm = sub.add_parser("confirm", help="check a recorded rewrite against production on fresh rows only")
    common(confirm)
    confirm.add_argument("digest", help="question-set digest (see `ledger`)")
    confirm.add_argument("--json", action="store_true")

    reset = sub.add_parser("reset", help="start the next run from production wording")
    common(reset, jev=False)
    reset.add_argument(
        "--rotate-split", action="store_true", help="also start a new split epoch (fresh held-out split)"
    )
    return parser


def _settings(args: argparse.Namespace, env: Mapping[str, str] | None, read_key: Callable[[str], str]) -> Any:
    from shared.jev import JevSettings

    settings = JevSettings.from_env(env)
    if args.prompt_key:
        try:
            entered = read_key(KEY_PROMPT)
        except EOFError:
            entered = ""
        settings = dataclasses.replace(settings, api_key=entered.strip() or None)
    return settings


def _decider(
    args: argparse.Namespace, env: Mapping[str, str] | None, read_key: Callable[[str], str], transport: Any
) -> Any:
    """A :class:`LabDecider`, or ``None`` after printing why Jev is not configured."""
    from shared.jev import JevDecider
    from shared.jev.settings import API_KEY_ENV, ENABLED_ENV

    from .jev_access import FAKE, LIVE, LabDecider, build_decider

    if args.fake:
        return LabDecider(build_decider(FAKE), mode=FAKE, max_requests=args.max_jev_requests)
    settings = _settings(args, env, read_key)
    if not settings.enabled:
        reason = f"{API_KEY_ENV} is not set" if not settings.api_key else f"{ENABLED_ENV} switches Jev off"
        print(
            f"{PROG}: not configured: {reason}. Nothing was sent. "
            "Set the key in your shell, use --prompt-key, or run with --fake for the offline stand-in.",
            file=sys.stderr,
        )
        return None
    decider = (
        JevDecider(dataclasses.replace(settings, header_sample_values=0), transport=transport)
        if transport is not None
        else build_decider(LIVE, settings)
    )
    from .ledger import Ledger

    cache = None if args.no_cache else Ledger(args.home, mode=LIVE).cache_path
    return LabDecider(decider, mode=LIVE, max_requests=args.max_jev_requests, cache_path=cache)


def _banner(decider: Any) -> str:
    if decider.mode == "fake":
        return "Jev: OFFLINE FAKE (fake-jev-offline). Its answers are not Jev's; nothing leaves this machine."
    return f"Jev: live, model {decider.settings.model}. Header rows and question wording leave this machine."


def _free_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _open_without_exposing(url: str, ledger: Any) -> None:
    """Open ``url`` in a browser without putting its token on a command line.

    ``webbrowser.open(url)`` passes the URL to a helper process as an
    argument, where other users of the machine can read it (``ps``). Instead a
    small owner-only file that redirects to the URL is opened, and removed a
    minute later.
    """
    ledger.ensure()
    launcher = ledger.state_dir / f".open-{secrets.token_hex(8)}.html"
    redirect = f"<script>location.replace({json.dumps(url)})</script>"
    launcher.write_text(f'<!doctype html><meta charset="utf-8"><title>Jev Lab</title>{redirect}', encoding="utf-8")
    os.chmod(launcher, stat.S_IRUSR | stat.S_IWUSR)
    webbrowser.open(launcher.as_uri())
    timer = threading.Timer(60.0, lambda: launcher.unlink(missing_ok=True))
    timer.daemon = True
    timer.start()


def _any_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _metrics_lines(summary: Mapping[str, Any]) -> list[str]:
    lines = []
    for kind, sides in summary.items():
        for side, m in sides.items():
            lines.append(
                f"  {kind:<15} {side:<8} subjects {m['subjects']:>3}  accuracy {_pct(m['accuracy'])}  "
                f"Brier {_num(m['brier'])}  ECE {_num(m['ece'])}  wrong>=auto {m['wrong_at_auto_apply']}"
            )
    return lines


def _pct(value: float | None) -> str:
    return "  -  " if value is None else f"{value:6.1%}"


def _num(value: float | None) -> str:
    return "  -  " if value is None else f"{value:.4f}"


def _cmd_serve(args: argparse.Namespace, decider: Any, ledger: Any) -> int:
    import uvicorn

    from .server import Lab, create_app

    if args.port == 0:
        args.port = _any_free_port()
    if not _free_port(args.port):
        print(f"{PROG}: error: port {args.port} on 127.0.0.1 is in use; pass --port", file=sys.stderr)
        return EXIT_USAGE
    backend = args.proposer or ("offline" if decider.mode == "fake" else "claude-cli")
    lab = Lab(decider=decider, ledger=ledger, proposer_backend=backend, proposer_model=args.model, port=args.port)
    url = f"http://127.0.0.1:{args.port}/#token={lab.token}"
    print(_banner(decider))
    print(f"Claude: {backend} ({args.model if backend != 'offline' else 'heuristic, not Claude'})")
    print(f"Budget: up to {decider.max_requests} Jev requests in this session. Ledger: {ledger.home}")
    print(f"Open: {url}")
    print("The token in that link is this session's key to the page. Ctrl-C stops the lab.")
    if not args.no_open:
        _open_without_exposing(url, ledger)
    config = uvicorn.Config(
        create_app(lab),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        access_log=False,
        timeout_graceful_shutdown=3,
    )
    server = uvicorn.Server(config)
    lab.shutting_down = lambda: server.should_exit  # open pages' event streams end on Ctrl-C
    server.run()
    return EXIT_OK


def _cmd_loop(args: argparse.Namespace, decider: Any, ledger: Any) -> int:
    from .loop import LoopConfig, run_loop
    from .proposer import ProposerError, build_proposer

    backend = args.proposer or ("offline" if decider.mode == "fake" else "claude-cli")
    try:
        proposer = build_proposer(backend, model=args.model)
    except ProposerError as exc:
        print(f"{PROG}: not configured: {exc}", file=sys.stderr)
        return EXIT_NOT_CONFIGURED
    if not args.json:
        print(_banner(decider))
        print(f"Claude: {backend}. Up to {args.generations} generations, {decider.max_requests} Jev requests.")

    def emit(event: str, data: Mapping[str, Any]) -> None:
        if args.json:
            return
        if event == "evaluated" and data["generation"] == 0:
            print("Incumbent:")
            print("\n".join(_metrics_lines(data["metrics"])))
        elif event == "generation_done":
            line = f"Generation {data['generation']}: {data['outcome']}"
            if data.get("accepted"):
                line += f" ({', '.join(data['accepted'])})"
            print(line)
            for kind, decision in (data.get("decisions") or {}).items():
                for reason in decision.get("reasons", [])[:3]:
                    print(f"  {kind}: {reason}")
            if data.get("reason"):
                print(f"  {data['reason']}")

    summary = run_loop(
        ledger=ledger,
        decider=decider,
        proposer=proposer,
        config=LoopConfig(generations=args.generations, margin=args.margin),
        emit=emit,
    )
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"Stopped: {summary['stopped']}. Accepted: {summary['accepted']}. "
            f"Jev requests sent: {summary['jev']['sent']}."
        )
        print("\n".join(_metrics_lines(summary["metrics"])))
    return EXIT_UNAVAILABLE if summary["stopped"].startswith("jev unavailable") else EXIT_OK


def _cmd_score(args: argparse.Namespace, decider: Any, ledger: Any) -> int:
    from shared.jev import JevUnavailable

    from .loop import evaluate_once

    try:
        result = evaluate_once(ledger, decider)
    except JevUnavailable as exc:
        print(f"{PROG}: unavailable: {exc.reason}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_banner(decider))
        print("\n".join(_metrics_lines(result["metrics"])))
    return EXIT_OK


def _cmd_confirm(args: argparse.Namespace, decider: Any, ledger: Any) -> int:
    from shared.jev import JevUnavailable

    from .loop import MIN_FRESH_SUBJECTS, confirm

    try:
        result = confirm(ledger, decider, ledger.load_set(args.digest))
    except JevUnavailable as exc:
        print(f"{PROG}: unavailable: {exc.reason}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    if args.json:
        print(json.dumps(result, indent=2))
        return EXIT_OK
    print(_banner(decider))
    print(f"{result['kind']}: {result['fresh_subjects']} fresh subjects in {result['fresh_cases']} fresh rows.")
    if not result["sufficient"]:
        print(
            f"Insufficient fresh data: label at least {MIN_FRESH_SUBJECTS} subjects in the sandbox "
            "after the split began."
        )
    for name in ("production", "rewrite"):
        m = result[name]
        print(
            f"  {name:<10} accuracy {_pct(m['accuracy'])}  Brier {_num(m['brier'])}  "
            f"wrong>=auto {m['wrong_at_auto_apply']}"
        )
    if result["decision"]:
        reasons = result["decision"]["reasons"]
        print("Holds on fresh rows." if not reasons else "Does not hold on fresh rows: " + "; ".join(reasons))
    return EXIT_OK


PROMOTION_FILES = {
    "header_mapping": "services/shared/jev/header_mapping.py (CANONICAL_FIELDS, and task/guidance in build_questions)",
    "file_cte": "services/shared/jev/cte_classification.py (CTE_CRITERIA, and task/guidance in _question)",
}


def _cmd_ledger(args: argparse.Namespace, ledger: Any) -> int:
    rows = ledger.generations()
    if args.json:
        print(json.dumps(rows, indent=2))
        return EXIT_OK
    if not rows:
        print(f"No generations recorded in {ledger.home}.")
    trusted = ledger.live_runs() if ledger.mode == "live" else set()
    for row in rows:
        decisions = row.get("decisions") or {}
        kept = ", ".join(row.get("accepted") or []) or "-"
        judge = "" if row.get("run_id") in trusted else "  [offline fake, not Jev]"
        print(f"{row['at']}  run {row['run_id']}  g{row['generation']}  {row['outcome']:<11} kept: {kept}{judge}")
        for kind, digest in (row.get("candidates") or {}).items():
            reasons = decisions.get(kind, {}).get("reasons") or []
            print(f"    {kind:<15} {digest[:12]}  {reasons[0] if reasons else 'accepted'}")
    for kind, qs in ledger.incumbents().items():
        print(f"Incumbent {kind}: {qs.label} {qs.digest}")
    return EXIT_OK


def _cmd_export(args: argparse.Namespace, ledger: Any) -> int:
    from .questions import baseline, changed_options

    if args.digest == "incumbent":
        found = list(ledger.incumbents().values())
    else:
        loaded = ledger.load_set(args.digest)
        if loaded is None:
            print(f"{PROG}: error: no question set {args.digest!r} in {ledger.home}", file=sys.stderr)
            return EXIT_USAGE
        found = [loaded]
    for qs in found:
        base = baseline(qs.kind)
        changed = changed_options(base, qs)
        print(f"# {qs.kind}: {qs.label} ({qs.digest})")
        print(f"# differs from production {base.label} in: {', '.join(changed) or 'nothing'}")
        for name in changed:
            old = getattr(base, name) if name in ("task", "guidance") else base.criteria.get(name)
            new = getattr(qs, name) if name in ("task", "guidance") else qs.criteria.get(name)
            print(
                f"\n## {name}\n- production: {json.dumps(old, ensure_ascii=False)}"
                f"\n+ candidate:  {json.dumps(new, ensure_ascii=False)}"
            )
        print("\n" + json.dumps(qs.to_dict(), indent=1, ensure_ascii=False))
        if changed and ledger.judged_by_fake(qs.digest):
            print(
                "\nJudged by the OFFLINE FAKE Jev, not by Jev: this is no evidence for production. "
                "Run the loop live to get a rewrite worth promoting."
            )
        elif changed:
            print(
                "\nPromotion is a pull request a person reviews:\n"
                f"  1. Apply the wording above to {PROMOTION_FILES[qs.kind]}.\n"
                f"  2. Bump QUESTIONS_VERSION from {base.label} and update every pin: "
                f"grep -rn '{base.label}' services docs\n"
                f"  3. Check it on rows the loop never saw: venv/bin/python scripts/jev_lab confirm {qs.digest}\n"
                "  4. Run python3 scripts/jev_eval.py with the live key and put its report in the PR."
            )
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    transport: Any | None = None,
    read_key: Callable[[str], str] = getpass.getpass,
) -> int:
    """Run one command. ``env``, ``transport`` and ``read_key`` exist for offline tests."""
    from .ledger import Ledger

    try:
        args = _parser().parse_args(list(argv) if argv is not None else (sys.argv[1:] or ["serve"]))
        if args.command is None:
            raise _UsageError("choose a command: serve, loop, score, ledger, export or reset")
        if getattr(args, "max_jev_requests", 1) < 1:
            raise _UsageError("--max-jev-requests must be at least 1")
        if args.command == "loop" and not 1 <= args.generations <= 25:
            raise _UsageError("--generations must be 1 to 25")
        if args.command == "loop" and not (math.isfinite(args.margin) and 0.0 <= args.margin <= 0.5):
            raise _UsageError("--margin must be a number from 0 to 0.5")
    except _UsageError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    ledger = Ledger(args.home, mode="fake" if args.fake else "live")
    if args.command == "ledger":
        return _cmd_ledger(args, ledger)
    if args.command == "export":
        return _cmd_export(args, ledger)
    if args.command == "reset":
        if args.rotate_split:
            ledger.rotate_split()
            print("New split epoch: a fresh held-out split, and rows labelled so far join the split.")
        else:
            ledger.reset()
        print(f"The next run starts from the production wording. History kept in {ledger.home}.")
        return EXIT_OK
    if args.command == "confirm" and ledger.load_set(args.digest) is None:
        print(f"{PROG}: error: no question set {args.digest!r} in {ledger.home}", file=sys.stderr)
        return EXIT_USAGE

    decider = _decider(args, env, read_key, transport)
    if decider is None:
        return EXIT_NOT_CONFIGURED
    ledger.ensure()
    try:
        if args.command == "serve":
            return _cmd_serve(args, decider, ledger)
        if args.command == "loop":
            return _cmd_loop(args, decider, ledger)
        if args.command == "confirm":
            return _cmd_confirm(args, decider, ledger)
        return _cmd_score(args, decider, ledger)
    finally:
        decider.close()
