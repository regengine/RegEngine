"""Offline checks for the auxiliary Supabase lead intake runbook."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

RUNBOOK = Path(__file__).resolve().parents[2] / "runbooks/supabase-assessment-lead-abuse-guard.sql"
OLDER_RUNBOOK = Path(__file__).resolve().parents[2] / "runbooks/supabase-anon-lead-capture-lockdown.sql"
FUNCTION_SIGNATURE = "CREATE OR REPLACE FUNCTION public.submit_assessment_lead(payload jsonb)"
SCHEMA = """
CREATE ROLE anon LOGIN;
CREATE ROLE authenticated LOGIN;
CREATE TABLE public.assessment_submissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    name text, email text, company text, role text, facility_count text,
    phone text, annual_revenue text, current_system text, biggest_retailer text,
    compliance_deadline text, recent_fda_inspection text, product_categories text,
    quiz_score numeric, quiz_grade text, quiz_answers jsonb, tool_inputs jsonb,
    source text, utm_source text, utm_medium text, utm_campaign text, referrer text
);
ALTER TABLE public.assessment_submissions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.assessment_submissions FROM PUBLIC;
"""


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    # Every psql call also supplies an explicit local Unix socket, port and DB.
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    result = subprocess.run(args, capture_output=True, text=True, env=env, check=False)
    if check and result.returncode:
        pytest.fail(f"{' '.join(args[:1])} failed: {result.stderr}")
    return result


@pytest.fixture(scope="module")
def postgres():
    if not all(shutil.which(binary) for binary in ("initdb", "pg_ctl", "psql")):
        pytest.skip("local PostgreSQL binaries are unavailable")

    with tempfile.TemporaryDirectory(prefix="regengine-supabase-test-") as temp:
        root = Path(temp)
        data = root / "data"
        socket = root / "socket"
        socket.mkdir()
        port = 40000 + os.getpid() % 20000
        _run(
            [
                "initdb",
                "-D",
                str(data),
                "-A",
                "trust",
                "-U",
                "postgres",
                "-c",
                "shared_memory_type=mmap",
                "--no-instructions",
            ]
        )
        _run(
            [
                "pg_ctl",
                "-D",
                str(data),
                "-l",
                str(root / "postgres.log"),
                "-o",
                f"-k {socket} -p {port} -c listen_addresses=''",
                "-w",
                "start",
            ]
        )
        connection = (
            "-X",
            "-w",
            "-A",
            "-t",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            str(socket),
            "-p",
            str(port),
            "-d",
            "postgres",
        )
        try:
            _run(["psql", *connection, "-U", "postgres", "-c", SCHEMA])
            _run(["psql", *connection, "-U", "postgres", "-f", str(RUNBOOK)])
            yield connection
        finally:
            _run(["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"])


@pytest.fixture(autouse=True)
def empty_submissions(postgres):
    _sql(postgres, "TRUNCATE public.assessment_submissions;", role="postgres")
    _sql(postgres, _function_ddl(RUNBOOK), role="postgres")


def _sql(postgres, sql: str, *, role: str = "anon", check: bool = True):
    return _run(["psql", *postgres, "-U", role, "-c", sql], check=check)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _function_ddl(runbook: Path) -> str:
    # The older lockdown script also changes unrelated policies and tables.
    # Reapply its real function body without requiring a mock of that whole schema.
    sql = runbook.read_text()
    start = sql.index(FUNCTION_SIGNATURE)
    end = sql.index("$fn$;", start) + len("$fn$;")
    return sql[start:end]


def _submit(postgres, payload: dict, *, check: bool = True):
    return _sql(postgres, f"SELECT public.submit_assessment_lead({_literal(json.dumps(payload))}::jsonb);", check=check)


def _rows(postgres):
    result = _sql(
        postgres,
        "SELECT coalesce(json_agg(to_jsonb(s) ORDER BY s.created_at, s.id), '[]'::json) "
        "FROM public.assessment_submissions s;",
        role="postgres",
    )
    return json.loads(result.stdout.strip()) or []


def test_initial_submission_and_anonymous_duplicate_preserve_row(postgres):
    _submit(
        postgres,
        {
            "email": " First@Example.com ",
            "name": "First",
            "company": "Original",
            "phone": "111",
            "facility_count": "2",
            "source": "quiz",
        },
    )
    original = _rows(postgres)
    assert len(original) == 1
    assert original[0]["email"] == "first@example.com"
    assert original[0]["phone"] == "111"

    _submit(
        postgres,
        {
            "email": "FIRST@example.com",
            "name": "Attacker",
            "company": "Changed",
            "phone": "999",
            "facility_count": "999",
            "annual_revenue": "changed",
            "source": "different",
        },
    )
    assert _rows(postgres) == original


def test_validation_and_global_rate_limit_still_apply(postgres):
    invalid = _submit(postgres, {"email": "invalid", "name": "N", "company": "C"}, check=False)
    assert invalid.returncode != 0
    assert "invalid email" in invalid.stderr
    assert _rows(postgres) == []

    _sql(
        postgres,
        "INSERT INTO public.assessment_submissions (name, email, company) "
        "SELECT 'N', n::text || '@example.com', 'C' FROM generate_series(1, 60) n;",
        role="postgres",
    )
    limited = _submit(postgres, {"email": "new@example.com", "name": "N", "company": "C"}, check=False)
    assert limited.returncode != 0
    assert "rate_limited" in limited.stderr
    assert len(_rows(postgres)) == 60


def test_same_email_after_24_hours_creates_a_new_row(postgres):
    payload = {"email": "again@example.com", "name": "N", "company": "C"}
    _submit(postgres, payload)
    _sql(
        postgres,
        "UPDATE public.assessment_submissions SET created_at = now() - interval '25 hours';",
        role="postgres",
    )

    _submit(postgres, payload)
    assert len(_rows(postgres)) == 2


@pytest.mark.parametrize(
    "reapply_order",
    [(OLDER_RUNBOOK, RUNBOOK), (RUNBOOK, OLDER_RUNBOOK)],
    ids=["lockdown-then-guard", "guard-then-lockdown"],
)
def test_reapplying_either_runbook_cannot_overwrite_duplicate(postgres, reapply_order):
    _submit(postgres, {"email": "reapply@example.com", "name": "First", "company": "C", "phone": "111"})
    original = _rows(postgres)

    for runbook in reapply_order:
        _sql(postgres, _function_ddl(runbook), role="postgres")
        _submit(postgres, {"email": "reapply@example.com", "name": "Changed", "company": "C", "phone": "999"})
        assert _rows(postgres) == original


def test_concurrent_anonymous_duplicates_create_one_row(postgres):
    barrier = threading.Barrier(8)

    def submit(index: int):
        barrier.wait(timeout=10)
        return _submit(
            postgres,
            {
                "email": "same@example.com",
                "name": f"Lead {index}",
                "company": "Company",
            },
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit, range(8)))

    assert all(result.returncode == 0 for result in results)
    assert len(_rows(postgres)) == 1
