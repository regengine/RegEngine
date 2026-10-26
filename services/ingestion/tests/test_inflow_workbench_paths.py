from __future__ import annotations

import json
import uuid

import app.inflow_workbench as workbench
import pytest
from fastapi import HTTPException


@pytest.fixture
def store_root(tmp_path, monkeypatch):
    root = tmp_path / uuid.uuid4().hex
    root.mkdir()
    monkeypatch.setenv("REGENGINE_INFLOW_WORKBENCH_PATH", str(root / "workbench.json"))
    return root


@pytest.mark.parametrize("tenant_prefix", ["../", "../../", "/", "..\\", "\x00"])
def test_tenant_input_cannot_escape_store_directory(store_root, tenant_prefix):
    tenant_id = tenant_prefix + str(uuid.uuid4())
    path = workbench._store_path(tenant_id)

    assert path.parent == store_root
    workbench._write_store(tenant_id, workbench._empty_store())
    assert workbench._read_store(tenant_id) == workbench._empty_store()
    assert list(store_root.iterdir()) == [path]


@pytest.mark.parametrize("operation", ["read", "write"])
@pytest.mark.parametrize("outside_root", [False, True])
def test_store_rejects_existing_symlinks(store_root, operation, outside_root):
    tenant_id = str(uuid.uuid4())
    target = (store_root.parent if outside_root else store_root) / f"{uuid.uuid4().hex}.json"
    payload = {"scenarios": [], "runs": {uuid.uuid4().hex: {}}, "fix_queue": {}}
    target.write_text(json.dumps(payload), encoding="utf-8")
    path = workbench._store_path(tenant_id)
    path.symlink_to(target)

    with pytest.raises(HTTPException) as error:
        if operation == "read":
            workbench._read_store(tenant_id)
        else:
            workbench._write_store(tenant_id, workbench._empty_store())

    assert error.value.status_code == 503
    assert json.loads(target.read_text(encoding="utf-8")) == payload


@pytest.mark.parametrize("operation", ["read", "write"])
def test_store_does_not_follow_symlink_created_after_path_check(store_root, monkeypatch, operation):
    tenant_id = str(uuid.uuid4())
    target = store_root.parent / f"{uuid.uuid4().hex}.json"
    payload = {"scenarios": [], "runs": {uuid.uuid4().hex: {}}, "fix_queue": {}}
    target.write_text(json.dumps(payload), encoding="utf-8")
    original_store_path = workbench._store_path

    def swap_path(tenant):
        path = original_store_path(tenant)
        path.symlink_to(target)
        return path

    monkeypatch.setattr(workbench, "_store_path", swap_path)
    if operation == "read":
        with pytest.raises(HTTPException) as error:
            workbench._read_store(tenant_id)
        assert error.value.status_code == 503
        assert error.value.detail == "Workbench persistence unavailable"
    else:
        with pytest.raises(OSError):
            workbench._write_store(tenant_id, workbench._empty_store())

    assert json.loads(target.read_text(encoding="utf-8")) == payload


@pytest.mark.parametrize("store_state", ["missing", "invalid_json"])
def test_normal_unavailable_store_read_keeps_empty_fallback(store_root, store_state):
    tenant_id = str(uuid.uuid4())
    if store_state == "invalid_json":
        workbench._store_path(tenant_id).write_text("{", encoding="utf-8")

    assert workbench._read_store(tenant_id) == workbench._empty_store()


def test_tenants_with_same_sanitized_prefix_keep_distinct_stores(store_root):
    component = uuid.uuid4().hex
    first = f"{component}/"
    second = f"{component}_"
    assert workbench._store_path(first) != workbench._store_path(second)
