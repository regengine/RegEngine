"""regctl must never persist full tenant API keys.

The local tenants file is a provisioning record, not an auth database.
The full key is shown once at creation; only a SHA-256 hash plus a
masked hint may be written to disk, and list output must stay masked.
"""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_regctl():
    # tenant.py imports Neo4jClient at module top; stub it so the test does
    # not need a live Neo4j driver.
    stub_names = (
        "services",
        "services.graph",
        "services.graph.app",
        "services.graph.app.neo4j_utils",
    )
    import types

    with pytest.MonkeyPatch.context() as mp:
        created = []
        for name in stub_names:
            if name not in sys.modules:
                mod = types.ModuleType(name)
                mp.setitem(sys.modules, name, mod)
                created.append(name)
        sys.modules["services.graph.app.neo4j_utils"].Neo4jClient = object
        spec = importlib.util.spec_from_file_location(
            "regctl_tenant_storage", ROOT / "scripts" / "regctl" / "tenant.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["regctl_tenant_storage"] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop("regctl_tenant_storage", None)
            for name in created:
                sys.modules.pop(name, None)
    return module


def test_save_never_writes_plaintext_key(tmp_path):
    module = _load_regctl()
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    full_key = f"sk_live_{uuid4().hex}"

    manager._save_tenant_record(uuid4(), "Hash Co", full_key)

    raw = Path(manager.tenants_db_file).read_bytes().decode("utf-8")
    assert full_key not in raw
    stored = [json.loads(line) for line in raw.splitlines()]
    assert "api_key" not in stored[0]
    assert stored[0]["api_key_hash"] == hashlib.sha256(full_key.encode()).hexdigest()
    assert stored[0]["api_key_hint"] == module.mask_api_key(full_key)
    assert full_key not in stored[0]["api_key_hint"]


def test_list_output_stays_masked(tmp_path, capsys):
    module = _load_regctl()
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    full_key = f"sk_live_{uuid4().hex}"
    manager._save_tenant_record(uuid4(), "List Co", full_key)

    manager.list_tenants()
    out = capsys.readouterr().out
    assert full_key not in out
    assert full_key[-4:] in out


def test_rewrite_scrubs_legacy_plaintext_key(tmp_path):
    module = _load_regctl()
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    legacy_key = f"sk_live_{uuid4().hex}"
    keep_id = uuid4()
    drop_id = uuid4()
    legacy = {
        "tenant_id": str(keep_id),
        "name": "Legacy Co",
        "api_key": legacy_key,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    doomed = {
        "tenant_id": str(drop_id),
        "name": "Gone Co",
        "api_key_hash": "abc",
        "api_key_hint": "***",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    Path(manager.tenants_db_file).write_text(json.dumps(legacy) + "\n" + json.dumps(doomed) + "\n")

    manager._remove_tenant_record(drop_id)

    raw = Path(manager.tenants_db_file).read_text()
    assert legacy_key not in raw
    stored = [json.loads(line) for line in raw.splitlines()]
    assert len(stored) == 1
    assert "api_key" not in stored[0]
    assert stored[0]["api_key_hash"] == hashlib.sha256(legacy_key.encode()).hexdigest()


def test_legacy_plaintext_record_lists_masked(tmp_path, capsys):
    module = _load_regctl()
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    legacy_key = f"sk_live_{uuid4().hex}"
    Path(manager.tenants_db_file).write_text(
        json.dumps(
            {
                "tenant_id": str(uuid4()),
                "name": "Old Co",
                "api_key": legacy_key,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
        + "\n"
    )

    manager.list_tenants()
    out = capsys.readouterr().out
    assert legacy_key not in out
    assert legacy_key[-4:] in out


def test_save_scrubs_legacy_plaintext_key(tmp_path, capsys):
    module = _load_regctl()
    manager = module.TenantManager()
    manager.tenants_db_file = str(tmp_path / ".tenants.db")
    legacy_key = f"sk_live_{uuid4().hex}"
    Path(manager.tenants_db_file).write_text(
        json.dumps(
            {
                "tenant_id": str(uuid4()),
                "name": "Old Co",
                "api_key": legacy_key,
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        )
        + "\n"
    )

    new_key = f"sk_live_{uuid4().hex}"
    manager._save_tenant_record(uuid4(), "New Co", new_key)

    raw = Path(manager.tenants_db_file).read_text()
    assert legacy_key not in raw
    assert new_key not in raw
    stored = [json.loads(line) for line in raw.splitlines()]
    assert len(stored) == 2
    assert all("api_key" not in record for record in stored)
    assert stored[0]["api_key_hash"] == hashlib.sha256(legacy_key.encode()).hexdigest()

    manager.list_tenants()
    out = capsys.readouterr().out
    assert legacy_key not in out
    assert new_key not in out
