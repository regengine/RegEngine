"""#2848 — audit persistence must never run on the event loop.

``FSMAAuditLog.log`` drives synchronous psycopg2 inserts with retry. Called
inline from an ``async def`` handler it blocks the entire Uvicorn event loop —
every concurrent request in the worker, ``/health`` and ``/readiness``
included — for as long as Postgres is slow or unreachable. A DB slowdown then
cascades into the platform reporting itself unhealthy.

``alog`` is the off-loop path. These tests pin both halves:

* the behaviour — ``alog`` really does run the blocking write on a worker
  thread and keeps the loop responsive;
* the invariant — no ``async def`` in the graph service calls the blocking
  writer directly. That is the part that regresses silently: the sync call is
  a single line that looks correct and passes every functional test.
"""

from __future__ import annotations

import ast
import asyncio
import sys
import threading
import time
from pathlib import Path

import pytest

_SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SERVICE_ROOT))

import services.graph.app.fsma_audit as fsma_audit  # noqa: E402
from services.graph.app.fsma_audit import FSMAAuditAction, FSMAAuditLog  # noqa: E402

_APP_DIR = _SERVICE_ROOT / "app"

# The synchronous entry points into audit persistence. Reaching any of these
# from an ``async def`` puts a psycopg2 round-trip (plus retries) on the loop.
_BLOCKING_AUDIT_CALLS = frozenset(
    {
        "log_extraction",
        "log_modification",
        "log_approval",
        "log_read_access",
        "log_trace_query",
        "log_export",
        "log_recall",
    }
)


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(fsma_audit, "_get_audit_db_engine", lambda: None)


# ---------------------------------------------------------------------------
# Behaviour: alog keeps the loop free
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alog_runs_the_blocking_write_off_the_loop(monkeypatch):
    """The psycopg2 insert must land on a worker thread, not the loop."""
    loop_thread_id = threading.get_ident()
    persist_thread_ids: list[int] = []

    def _persist(_entry):
        persist_thread_ids.append(threading.get_ident())
        return True

    monkeypatch.setattr(fsma_audit, "_persist_audit_entry", _persist)

    await FSMAAuditLog(max_entries=16).alog(
        action=FSMAAuditAction.KDE_READ,
        target_type="KDE",
        target_id="LOT-1",
        tenant_id="tenant-a",
    )

    assert persist_thread_ids, "the audit write never happened"
    assert loop_thread_id not in persist_thread_ids, (
        f"audit persistence ran on the event loop thread (loop={loop_thread_id}, calls={persist_thread_ids})"
    )


@pytest.mark.asyncio
async def test_slow_audit_write_does_not_stall_the_loop(monkeypatch):
    """A slow audit DB must not freeze concurrent work.

    The write blocks for 250ms while a ticker runs every 10ms. Off the loop
    the ticker keeps going; on the loop it cannot run at all.
    """
    block_seconds = 0.25
    tick_interval = 0.01
    ticks = 0

    async def _ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(tick_interval)
            ticks += 1

    def _slow_persist(_entry):
        time.sleep(block_seconds)
        return True

    monkeypatch.setattr(fsma_audit, "_persist_audit_entry", _slow_persist)

    ticker_task = asyncio.create_task(_ticker())
    try:
        await asyncio.sleep(tick_interval * 2)
        ticks_before = ticks

        await FSMAAuditLog(max_entries=16).alog(
            action=FSMAAuditAction.KDE_READ,
            target_type="KDE",
            target_id="LOT-1",
            tenant_id="tenant-a",
        )
    finally:
        ticker_task.cancel()

    ticks_during = ticks - ticks_before
    assert ticks_during >= 5, (
        f"event loop was stalled by the audit write: only {ticks_during} ticks in {block_seconds}s"
    )


# ---------------------------------------------------------------------------
# Invariant: no async handler calls the blocking writer
# ---------------------------------------------------------------------------


def _calls_in(node: ast.AST):
    """Yield Call nodes lexically inside ``node``, without descending into
    nested function bodies or lambdas — a sync closure defined inside an
    ``async def`` is exactly how you *correctly* hand work to a thread."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Call):
            yield child
        yield from _calls_in(child)


def _blocking_audit_call_name(call: ast.Call) -> str | None:
    """Return a label if ``call`` is a synchronous audit write."""
    func = call.func

    # get_audit_log().log(...) / <anything>.log(...) on a get_audit_log() result
    if isinstance(func, ast.Attribute) and func.attr == "log":
        inner = func.value
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == "get_audit_log":
            return "get_audit_log().log(...)"

    # Module-level convenience wrappers, which call .log() internally.
    if isinstance(func, ast.Name) and func.id in _BLOCKING_AUDIT_CALLS:
        return f"{func.id}(...)"

    return None


def _async_blocking_audit_sites() -> list[str]:
    findings: list[str] = []
    for path in sorted(_APP_DIR.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover - not our problem to report here
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for call in _calls_in(node):
                label = _blocking_audit_call_name(call)
                if label:
                    rel = path.relative_to(_SERVICE_ROOT.parent.parent)
                    findings.append(f"{rel}:{call.lineno} in async def {node.name}(): {label}")
    return findings


def test_no_async_function_calls_the_blocking_audit_writer():
    """Async code must use ``await get_audit_log().alog(...)`` instead.

    ``routers/lineage_traversal.py`` was the last holdout (#2848); the four
    KDE_READ sites in ``routers/fsma/traceability.py`` were converted earlier.
    """
    findings = _async_blocking_audit_sites()

    assert not findings, "synchronous audit writes reachable from the event loop:\n  " + "\n  ".join(findings)


def test_the_guard_can_actually_fail():
    """Guard the guard: the detector must recognise the pattern it hunts."""
    tree = ast.parse(
        "async def handler():\n"
        "    get_audit_log().log(action=1)\n"
        "    def inner():\n"
        "        get_audit_log().log(action=2)\n"
        "    log_read_access(target_id='x')\n"
    )
    async_def = tree.body[0]
    labels = [_blocking_audit_call_name(c) for c in _calls_in(async_def)]
    found = [label for label in labels if label]

    # The nested sync ``inner`` is deliberately not reported.
    assert found == ["get_audit_log().log(...)", "log_read_access(...)"]
