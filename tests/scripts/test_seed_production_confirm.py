"""Production demo-seed writes need an explicit flag plus typed confirmation.

Covers audit finding 65: scripts/seed_founder_demo_ctes.py and
scripts/seed_agent_review_demo.py must require typed confirmation and
log/audit production use. These tests fail on the old code (flag alone
allows the write, and no AUDIT line is emitted) and pass on the new code.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
PROD_BASE = "https://regengine-production.up.railway.app"
PROD_DB_URL = "postgresql://regengine:s3cret@db.example.supabase.co:5432/postgres"
CONFIRM = "SEED-PRODUCTION"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _clear_prod_env(monkeypatch):
    for marker in (
        "REGENGINE_ENV",
        "ENV",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_SERVICE_NAME",
        "VERCEL_ENV",
        "VERCEL_URL",
    ):
        monkeypatch.delenv(marker, raising=False)


def test_founder_prod_write_without_confirm_is_refused(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "hmac-secret")
    called = []

    def fake_post_batch(*args, **kwargs):
        called.append(True)
        return {"accepted": 1, "rejected": 0, "events": []}

    monkeypatch.setattr(mod, "post_batch", fake_post_batch)
    rc = mod.main(["--base", PROD_BASE, "--allow-production"])
    assert rc == 2
    assert "confirm" in capsys.readouterr().out.lower()
    assert called == []


def test_founder_prod_write_with_wrong_confirm_is_refused(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "hmac-secret")
    called = []
    monkeypatch.setattr(mod, "post_batch", lambda *a, **k: (called.append(True), {"accepted": 0})[1])
    rc = mod.main(["--base", PROD_BASE, "--allow-production", "--confirm-production", "yes"])
    assert rc == 2
    assert called == []


def test_founder_prod_write_with_confirm_seeds_and_audits(monkeypatch, capsys):
    mod = _load("seed_founder_demo_ctes")
    monkeypatch.delenv("SEED_BASE_URL", raising=False)
    monkeypatch.setenv("REGENGINE_TENANT_API_KEY", "secret-from-env")
    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "hmac-secret")
    monkeypatch.setattr(
        mod,
        "post_batch",
        lambda *a, **k: {"accepted": 13, "rejected": 0, "events": []},
    )
    rc = mod.main(
        [
            "--base",
            PROD_BASE,
            "--allow-production",
            "--confirm-production",
            CONFIRM,
        ]
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "AUDIT" in err
    assert PROD_BASE in err


def test_agent_review_prod_write_with_flag_but_no_confirm_is_refused(monkeypatch, capsys):
    mod = _load("seed_agent_review_demo")
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", PROD_DB_URL)
    rc = mod.main(["--allow-production-demo-seed"])
    assert rc == 2
    assert "confirm" in capsys.readouterr().err.lower()


def test_agent_review_prod_write_without_any_flag_is_refused(monkeypatch, capsys):
    mod = _load("seed_agent_review_demo")
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", PROD_DB_URL)
    rc = mod.main([])
    assert rc == 2


def test_agent_review_prod_write_with_confirm_seeds_and_audits(monkeypatch, capsys):
    mod = _load("seed_agent_review_demo")
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", PROD_DB_URL)

    import shared.database as database_module

    seeded = []

    class FakeSession:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(database_module, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(
        mod,
        "seed_agent_review_demo",
        lambda session, artifacts: (
            seeded.append(True),
            mod.SeedResult(
                artifacts_created=5,
                artifacts_skipped=0,
                receipts_created=5,
                receipts_skipped=0,
            ),
        )[1],
    )
    rc = mod.main(["--allow-production-demo-seed", "--confirm-production", CONFIRM])
    assert rc == 0
    assert seeded == [True]
    err = capsys.readouterr().err
    assert "AUDIT" in err
    assert "s3cret" not in err


def test_agent_review_local_write_needs_no_confirm(monkeypatch, capsys):
    mod = _load("seed_agent_review_demo")
    _clear_prod_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine")

    import shared.database as database_module

    class FakeSession:
        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    served = []
    monkeypatch.setattr(database_module, "SessionLocal", lambda: FakeSession())

    def fake_seed(session, artifacts):
        served.append(True)
        return mod.SeedResult(
            artifacts_created=5,
            artifacts_skipped=0,
            receipts_created=5,
            receipts_skipped=0,
        )

    monkeypatch.setattr(mod, "seed_agent_review_demo", fake_seed)
    rc = mod.main([])
    assert rc == 0
    assert served == [True]
    assert "AUDIT" not in capsys.readouterr().err
