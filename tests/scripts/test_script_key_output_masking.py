"""Key output masking for operator scripts (code-scanning alerts 18, 19, 20, 42).

create_test_api_key.py must never print the raw key: it writes it to a
0600 file and prints only a masked form. export_env_bundle.py must never
print full credential values to a terminal; --allow-tty shows a masked
preview. Values here are random uuid4 strings, never real credentials.
"""

from __future__ import annotations

import importlib.util
import io
import json
import stat
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def keygen():
    return _load("test_support_create_test_api_key", SCRIPTS / "create_test_api_key.py")


@pytest.fixture()
def bundle():
    return _load("test_support_export_env_bundle", SCRIPTS / "export_env_bundle.py")


def _raw_key() -> str:
    return f"rge_{uuid.uuid4().hex[:12]}.{uuid.uuid4().hex}"


# --- create_test_api_key.py ---


def test_key_file_is_owner_only_and_holds_raw_key(keygen, tmp_path):
    raw = _raw_key()
    path = tmp_path / "nested" / "key"
    keygen._write_key_file(raw, path)
    assert path.read_text().strip() == raw
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_key_file_permissions_tightened_on_overwrite(keygen, tmp_path):
    target = tmp_path / "key"
    target.write_text("")
    target.chmod(0o644)
    keygen._write_key_file(_raw_key(), target)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_key_file_rejects_symlink_target(keygen, tmp_path):
    real = tmp_path / "real-target"
    real.write_text("placeholder")
    link = tmp_path / "key-link"
    link.symlink_to(real)
    with pytest.raises(SystemExit, match="symlink"):
        keygen._write_key_file(_raw_key(), link)
    # Symlink target must not have been overwritten with the raw key.
    assert real.read_text() == "placeholder"


def test_key_file_rejects_group_writable_parent(keygen, tmp_path):
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o755)
    parent.chmod(0o755)
    with pytest.raises(SystemExit, match="group/world"):
        keygen._write_key_file(_raw_key(), parent / "key")


def test_summary_never_contains_raw_key(keygen, tmp_path):
    raw = _raw_key()
    key_id, _, secret = raw.partition(".")
    summary = keygen._KeySummary(
        key_id=key_id,
        tenant_id=str(uuid.uuid4()),
        scopes=["webhooks.ingest"],
        billing_tier="ENTERPRISE",
        expires_at=None,
    )
    path = tmp_path / "key"
    text = keygen._format_summary(summary, path, "set to 'trialing'")

    assert raw not in text
    assert secret not in text
    assert key_id in text
    assert str(path) in text


def test_summary_shell_quotes_key_path_with_spaces(keygen, tmp_path):
    summary = keygen._KeySummary(
        key_id="rge_demo",
        tenant_id=str(uuid.uuid4()),
        scopes=["webhooks.ingest"],
        billing_tier="ENTERPRISE",
        expires_at=None,
    )
    path = tmp_path / "my key file"
    text = keygen._format_summary(summary, path, "set to 'trialing'")
    assert f'cat {path}' not in text  # unquoted path must not appear
    assert "cat 'my key file'" in text or 'cat "my key file"' in text or "cat 'my key file'" in text.replace(str(tmp_path)+"/", "")
    # shlex.quote on POSIX wraps spaces in single quotes
    import shlex
    assert f"cat {shlex.quote(str(path))}" in text


def test_key_file_flag_defaults_outside_repo(keygen, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["create_test_api_key.py"])
    args = keygen._parse_args()
    assert args.key_file == keygen.DEFAULT_KEY_FILE
    assert REPO_ROOT not in args.key_file.parents


# --- export_env_bundle.py ---


def test_mask_payload_hides_every_credential(bundle):
    secret_names = ["POSTGRES_PASSWORD", "NEO4J_PASSWORD", "KAFKA_PASSWORD",
                    "OBJECT_STORAGE_ACCESS_KEY_ID", "OBJECT_STORAGE_SECRET_ACCESS_KEY"]
    payload = {name: uuid.uuid4().hex for name in secret_names}
    payload["POSTGRES_HOST"] = "localhost"

    masked = bundle.mask_payload(payload)

    for name in secret_names:
        assert payload[name] not in masked[name]
    assert masked["POSTGRES_HOST"] == "localhost"


def test_every_payload_key_is_classified(bundle, monkeypatch):
    """New payload keys default to masked unless explicitly listed as non-secret."""
    payload = bundle.build_secret_payload("dev")
    for name in payload:
        if name not in bundle.NON_SECRET_KEYS:
            assert any(word in name for word in ("PASSWORD", "KEY", "SECRET", "USERNAME")), name


def test_allow_tty_prints_masked_preview_only(bundle, monkeypatch, tmp_path):
    values = {
        "POSTGRES_PASSWORD": uuid.uuid4().hex,
        "NEO4J_PASSWORD": uuid.uuid4().hex,
        "OBJECT_STORAGE_ACCESS_KEY_ID": uuid.uuid4().hex,
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": uuid.uuid4().hex,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    class _Tty(io.StringIO):
        def isatty(self):
            return True

    out = _Tty()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "argv", [
        "export_env_bundle.py", "--environment", "dev",
        "--env-file", str(tmp_path / "absent.env"), "--emit-bundle", "--allow-tty",
    ])

    bundle.main()

    printed = out.getvalue()
    for value in values.values():
        assert value not in printed
    preview = json.loads(printed)
    assert set(values) <= set(preview)


def test_tty_without_flag_is_refused(bundle, monkeypatch, tmp_path):
    for name in bundle.REQUIRED_SECRETS:
        monkeypatch.setenv(name, uuid.uuid4().hex)

    class _Tty(io.StringIO):
        def isatty(self):
            return True

    out = _Tty()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "argv", [
        "export_env_bundle.py", "--environment", "dev",
        "--env-file", str(tmp_path / "absent.env"), "--emit-bundle",
    ])
    with pytest.raises(SystemExit) as exc:
        bundle.main()
    assert exc.value.code == 2
    assert out.getvalue() == ""
