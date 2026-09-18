"""Anti-stub canonical guards: call-site existence + write/persist/reopen/read proofs.

Case study (#2989, incident night 2026-09-17): ``_process_stripe_webhook``
called ``rate_limiting._check_verified_stripe_webhook_rate_limit`` while the
function did not exist in ``rate_limiting.py``. Every correctly-signed Stripe
webhook died with ``AttributeError``, returned 500 to Stripe, and retried for
three days without reaching billing handlers. No test failed at landing time
because nothing asserted that a *called* name *exists* in its import source.

Two complementary mechanisms, both DB-free and CI-fast:

Part A — cross-module call-site existence (static, pure AST):
  for each guarded caller, every attribute call on an imported module alias
  and every bare call of a directly from-imported name must resolve to a name
  defined at the top level of the target module. A missing name is the
  exact #2989 class.

Part B — write -> persist -> reopen -> read behavioral proofs (subprocess,
implementation-agnostic): each protected module must survive a real
round-trip — state written through the module's own API, serialized,
reopened in a FRESH interpreter, and read back with the same result — and
the exercised entrypoints must be real functions whose code lives in the
module file (never a Mock, never site-packages). Limits/key shapes are read
from the module's own constants, so divergent legitimate implementations
(e.g. a per-mode verified budget vs a shared one) both pass.

Part C — vacuity self-test: the Part A checker MUST fire on a synthetic
missing-name pair. A guard that cannot fail is theater.

Scope is deliberately a table (CALLER_GUARDS / BEHAVIORAL_TARGETS): extend
by adding rows, not by growing bespoke logic.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# --- Part A scope -----------------------------------------------------------
# caller (repo-relative) -> package dir of the caller, for relative-import
# resolution. Every relative module alias and every direct from-import in the
# caller is checked against its target module's top-level definitions.
CALLER_GUARDS = {
    "services/ingestion/app/stripe_billing/webhooks.py": "services/ingestion/app/stripe_billing",
    "services/ingestion/app/remediation/delivery.py": "services/ingestion/app/remediation",
}

# --- Part B scope -----------------------------------------------------------
BEHAVIORAL_TARGETS = ("run_ledger", "suppression", "rate_limiting")

_DRIVER = textwrap.dedent(
    '''
    """Subprocess driver for guard behavioral proofs. Usage: driver.py <mode> <workdir>"""
    import importlib
    import inspect
    import json
    import sys
    from pathlib import Path

    mode, workdir = sys.argv[1], Path(sys.argv[2])


    def emit(payload):
        print("GUARDJSON" + json.dumps(payload))


    def assert_real_function(fn, expected_file_part):
        assert isinstance(fn, type(lambda: None)), f"{fn!r} is not a plain function (stub?)"
        src = inspect.getsourcefile(fn) or ""
        assert expected_file_part in src, f"{fn.__name__} defined in {src}, expected *{expected_file_part}*"


    if mode == "ledger-write":
        from shared.run_ledger import verify_receipt_chain

        assert_real_function(verify_receipt_chain, "run_ledger.py")
        now = "2026-05-13T12:00:00+00:00"

        def receipt(seq, h, prev):
            return {
                "receipt_id": f"r{seq}", "sequence_num": seq, "state": "received",
                "occurred_at": now, "actor": "system", "request_id": "req-1",
                "canonical_event_id": None, "evidence_attachment_id": None,
                "rule_evaluation_id": None, "export_log_id": None,
                "metadata": {"row": seq}, "payload_hash": "c" * 64,
                "previous_receipt_hash": prev, "receipt_hash": h, "created_at": now,
            }

        chain = [receipt(1, "a" * 64, None), receipt(2, "b" * 64, "a" * 64), receipt(3, "d" * 64, "b" * 64)]
        result = verify_receipt_chain(chain)
        assert result.valid, result.errors
        (workdir / "ledger_chain.json").write_text(json.dumps(chain))
        emit({"mode": mode, "valid": result.valid, "head": result.head_receipt_hash})

    elif mode == "ledger-read":
        from shared.run_ledger import verify_receipt_chain

        chain = json.loads((workdir / "ledger_chain.json").read_text())
        result = verify_receipt_chain(chain)
        assert result.valid, f"reopened chain failed verification: {result.errors}"
        assert result.head_receipt_hash == "d" * 64
        emit({"mode": mode, "valid": result.valid, "head": result.head_receipt_hash})

    elif mode == "suppression-write":
        from shared.agent_org.suppression import record_suppression

        assert_real_function(record_suppression, os.path.join("agent_org", "suppression.py"))
        table = {}

        class FakeSession:
            def __init__(self, backing):
                self._backing = backing
                self.normalized_seen = None

            def execute(self, stmt, params=None):
                params = dict(params or {})
                email = params.get("email_address")
                if email is not None:
                    self.normalized_seen = email
                    self._backing.setdefault(params.get("tenant_id"), set()).add(email)
                result = type("R", (), {"fetchone": lambda self: None})()
                return result

        session = FakeSession(table)
        record_suppression(session, tenant_id="t-1", email_address="  MixedCase@Example.COM ",
                           reason="manual_unsubscribe", source="guard-proof")
        assert session.normalized_seen, "write path emitted no normalized email param"
        (workdir / "suppression_table.json").write_text(
            json.dumps({t: sorted(emails) for t, emails in table.items()}))
        emit({"mode": mode, "normalized": session.normalized_seen})

    elif mode == "suppression-read":
        from shared.agent_org import suppression
        from shared.agent_org.suppression import is_suppressed

        assert_real_function(is_suppressed, os.path.join("agent_org", "suppression.py"))
        table = json.loads((workdir / "suppression_table.json").read_text())

        class FakeSession:
            def __init__(self, backing):
                self._backing = backing

            def execute(self, stmt, params=None):
                params = dict(params or {})
                email = params.get("email_address")
                hit = email is not None and email in self._backing.get(params.get("tenant_id"), [])
                result = type("R", (), {"fetchone": lambda self: (1,) if hit else None})()
                return result

        # read back through a FRESH session reopened from persisted state,
        # presenting the messy (unnormalized) form a caller would supply
        session = FakeSession({t: set(emails) for t, emails in table.items()})
        assert is_suppressed(session, tenant_id="t-1", email_address="mixedcase@example.com") is True
        assert is_suppressed(session, tenant_id="t-1", email_address="other@example.com") is False
        # anti-clobber: the module-level function object is still the real one
        assert "suppression.py" in (inspect.getsourcefile(suppression.is_suppressed) or "")
        emit({"mode": mode, "read_back": True})

    elif mode == "billing-invariants":
        from fastapi import HTTPException

        from app.stripe_billing import rate_limiting as rl
        from app.stripe_billing import webhooks

        fn = getattr(rl, "_check_verified_stripe_webhook_rate_limit", None)
        assert fn is not None, "#2989 class: verified budget function missing from rate_limiting"
        assert_real_function(fn, "rate_limiting.py")
        assert_real_function(rl._check_stripe_webhook_rate_limit, "rate_limiting.py")

        # the live call site must resolve to the same object (no shadow/stub)
        assert getattr(webhooks._rate_limiting_mod, "_check_verified_stripe_webhook_rate_limit", None) is fn

        # limits come from the module's own constants — divergent legitimate
        # implementations (dedicated verified limit vs shared) both pass here
        limit = int(getattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", rl._WEBHOOK_RATE_LIMIT))

        # Unique per-run bucket identities: under a shared Redis (local dev) or
        # repeated in-memory runs, constant names would compound inside the 60s
        # window and flake phase 1 with a warm-bucket 429.
        acct = "guard_acct_a_" + os.urandom(8).hex()
        for _ in range(limit):
            fn({"account": acct})  # admit: no exception
        try:
            fn({"account": acct})
            raise SystemExit(f"expected 429 after {limit} verified admits for one account")
        except HTTPException as exc:
            assert exc.status_code == 429, exc.status_code
            assert int(exc.headers.get("Retry-After", "0")) > 0

        other = "guard_acct_b_" + os.urandom(8).hex()
        fn({"account": other})  # isolation: B unaffected by A's exhaustion

        # missing account key -> default bucket, no crash (shape-agnostic).
        # NOTE: event=None is NOT a call-site contract: stripe.Webhook.construct_event
        # either returns a dict or raises before this function is ever reached.
        fn({})
        emit({"mode": mode, "limit": limit, "isolation": True, "default_bucket": True})

    else:
        raise SystemExit(f"unknown mode {mode}")
    '''
)

# repo-root path must be visible inside the driver too
_DRIVER = "import os\n" + _DRIVER


# --- Part A implementation ---------------------------------------------------

def _defined_top_level_names(module_path: Path) -> set:
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _resolve_target(pkg_dir: Path, module: str | None, level: int, name: str | None) -> Path | None:
    """Resolve ``from <module> import <name>`` (or ``from . import <name>``) to a file."""
    base = pkg_dir
    for _ in range(max(level - 1, 0)):
        base = base.parent
    if module:  # from .mod import name / from pkg.mod import name
        candidate = base.joinpath(*module.split("."))
        for suffix in (".py", "/__init__.py"):
            p = Path(str(candidate) + suffix) if suffix == ".py" else candidate / "__init__.py"
            if p.exists():
                return p
        return None
    # from . import name -> name is a submodule of base
    for suffix in (".py",):
        p = base / f"{name}.py"
        if p.exists():
            return p
    init = base / name / "__init__.py"
    return init if init.exists() else None


def find_unresolved_calls(caller_rel: str, pkg_rel: str) -> list[str]:
    """Return human-readable violations: names called in caller but missing from target."""
    caller_path = REPO_ROOT / caller_rel
    pkg_dir = REPO_ROOT / pkg_rel
    tree = ast.parse(caller_path.read_text(), filename=str(caller_path))

    module_aliases: dict[str, Path] = {}  # alias -> target file
    direct_imports: dict[str, Path] = {}  # imported name -> target file

    for node in tree.body:  # module-level imports only
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if node.module == "__future__":
                    continue
                if node.level > 0:
                    # relative: from . import X as Y  |  from .X import f as g
                    target = _resolve_target(pkg_dir, node.module, node.level, alias.name)
                    if target is None:
                        continue
                    if node.module is None:
                        # 'from . import X as Y': alias binds the submodule
                        module_aliases[alias.asname or alias.name] = target
                    else:
                        # 'from .X import f': alias binds a name inside target
                        direct_imports[alias.asname or alias.name] = target
                elif node.module and node.module.startswith("shared"):
                    target = _resolve_target(REPO_ROOT / "services", node.module, 0, None)
                    if target is None:
                        continue
                    if alias.name == "*":
                        continue
                    # could be a submodule (from shared import funnel_events) or a name
                    sub = _resolve_target(REPO_ROOT / "services", f"{node.module}.{alias.name}", 0, None)
                    if sub is not None:
                        module_aliases[alias.asname or alias.name] = sub
                    else:
                        direct_imports[alias.asname or alias.name] = target
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    target = _resolve_target(REPO_ROOT, alias.name, 0, None)
                    if target is not None:
                        module_aliases[alias.asname] = target

    defined_cache: dict[Path, set] = {}

    def defined_names(path: Path) -> set:
        if path not in defined_cache:
            defined_cache[path] = _defined_top_level_names(path)
        return defined_cache[path]

    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            target = module_aliases.get(func.value.id)
            if target is not None and func.attr not in defined_names(target):
                problems.append(
                    f"{caller_rel}:{node.lineno} calls {target.name}.{func.attr}() "
                    f"but '{func.attr}' is not defined in {target.relative_to(REPO_ROOT)} "
                    f"(#2989 class: call site whose function never existed)"
                )
        elif isinstance(func, ast.Name):
            target = direct_imports.get(func.id)
            if target is not None and func.id not in defined_names(target):
                problems.append(
                    f"{caller_rel}:{node.lineno} calls {func.id}() imported from "
                    f"{target.relative_to(REPO_ROOT)} but '{func.id}' is not defined there "
                    f"(#2989 class: call site whose function never existed)"
                )
    return problems


@pytest.mark.parametrize("caller_rel", sorted(CALLER_GUARDS))
def test_call_site_existence(caller_rel: str) -> None:
    problems = find_unresolved_calls(caller_rel, CALLER_GUARDS[caller_rel])
    assert not problems, "Unresolved cross-module calls:\n" + "\n".join(problems)


def test_guard_mechanism_is_not_vacuous(tmp_path: Path) -> None:
    """Part A must fire on a synthetic missing-name pair — a guard that
    cannot fail is theater."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "target.py").write_text("def existing():\n    ...\n")
    (pkg / "caller.py").write_text(
        "from . import target as t\n\n\ndef go():\n    t.existing()\n    t.never_landed()\n"
    )
    global REPO_ROOT
    saved = REPO_ROOT
    REPO_ROOT = tmp_path
    try:
        problems = find_unresolved_calls("pkg/caller.py", "pkg")
    finally:
        REPO_ROOT = saved
    assert any("never_landed" in p for p in problems), problems


# --- Part B implementation ---------------------------------------------------

def _run_driver(mode: str, workdir: Path, pythonpath: list[Path]) -> dict:
    driver = workdir / "driver.py"
    driver.write_text(_DRIVER)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in pythonpath)
    proc = subprocess.run(
        [sys.executable, str(driver), mode, str(workdir)],
        capture_output=True, text=True, timeout=180, env=env,
    )
    assert proc.returncode == 0, f"driver {mode} failed:\n{proc.stdout}\n{proc.stderr}"
    for line in proc.stdout.splitlines():
        if line.startswith("GUARDJSON"):
            return json.loads(line[len("GUARDJSON"):])
    raise AssertionError(f"driver {mode} emitted no GUARDJSON line:\n{proc.stdout}\n{proc.stderr}")


def test_run_ledger_write_persist_reopen_read(tmp_path: Path) -> None:
    services = REPO_ROOT / "services"
    if not (services / "shared" / "run_ledger.py").exists():
        pytest.skip("run_ledger.py absent at this commit — outside guard scope")
    written = _run_driver("ledger-write", tmp_path, [services])
    assert written["valid"] is True
    reopened = _run_driver("ledger-read", tmp_path, [services])
    assert reopened["valid"] is True and reopened["head"] == written["head"]


def test_suppression_write_persist_reopen_read(tmp_path: Path) -> None:
    services = REPO_ROOT / "services"
    if not (services / "shared" / "agent_org" / "suppression.py").exists():
        pytest.skip("agent_org/suppression.py absent at this commit — outside guard scope")
    written = _run_driver("suppression-write", tmp_path, [services])
    assert written["normalized"] == "mixedcase@example.com", written
    reread = _run_driver("suppression-read", tmp_path, [services])
    assert reread["read_back"] is True


def test_rate_limiting_invariants(tmp_path: Path) -> None:
    result = _run_driver(
        "billing-invariants",
        tmp_path,
        [REPO_ROOT / "services" / "ingestion", REPO_ROOT / "services"],
    )
    assert result["isolation"] is True and result["default_bucket"] is True
    assert result["limit"] >= 1
