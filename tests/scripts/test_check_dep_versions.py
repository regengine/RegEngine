"""Self-tests for the dependency version drift guard (#2936).

The guard used to read ``[tool.poetry.dependencies]`` from a
``pyproject.toml`` that declares none, print a WARNING, and return 0 before
opening a single requirements file — so the "Dep version drift guard" hard
gate in backend-ci.yml passed on every PR while checking nothing.

These tests pin the two properties that failure depended on: real drift must
exit 1, and an input-less run must exit 1 rather than green.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_dep_versions.py"


def _load_guard(repo_root: Path | None = None):
    spec = importlib.util.spec_from_file_location("_check_dep_versions", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if repo_root is not None:
        module.REPO_ROOT = repo_root
        module.REQUIREMENTS_IN = repo_root / "requirements.in"
        module.REQUIREMENTS_LOCK = repo_root / "requirements.lock"
    return module


guard = _load_guard()


def _fake_repo(tmp_path: Path, requirements_in: str, requirements_lock: str) -> Path:
    (tmp_path / "requirements.in").write_text(requirements_in)
    (tmp_path / "requirements.lock").write_text(requirements_lock)
    return tmp_path


# ---------------------------------------------------------------------------
# Version / specifier arithmetic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lower,higher",
    [
        ("0.140.0", "0.141.1"),
        ("2.0.52", "2.0.53"),
        ("1.19.1", "1.20.0"),
        ("2.13.4rc1", "2.13.4"),
        ("2.13.4.dev1", "2.13.4"),
        ("2.13.4", "2.13.4.post1"),
        ("1.9", "1.10"),
    ],
)
def test_version_ordering(lower, higher):
    assert guard.Version(lower) < guard.Version(higher)


def test_version_zero_padding():
    assert guard.Version("2.0") == guard.Version("2.0.0")


@pytest.mark.parametrize(
    "spec,pin,expected",
    [
        (">=0.141.1", "0.141.1", True),
        (">=0.141.1", "0.140.0", False),
        (">=2.13.4,<3", "2.13.4", True),
        (">=2.13.4,<3", "3.0.0", False),
        (">=2.13.4,<3", "2.99.0", True),
        ("~=1.19.1", "1.19.5", True),
        ("~=1.19.1", "1.20.0", False),
        ("==6.0.3", "6.0.3", True),
        ("==6.0.3", "6.0.4", False),
        ("", "1.2.3", True),
    ],
)
def test_specifier_allows(spec, pin, expected):
    ok, _clause = guard.specifier_allows(spec, guard.Version(pin))
    assert ok is expected


def test_name_normalisation():
    assert guard.normalise("PyJWT") == "pyjwt"
    assert guard.normalise("pydantic_settings") == "pydantic-settings"


def test_extras_are_split_off_the_package_name(tmp_path):
    """`httpx[http2]` in the .in and the lock must resolve to the same key.

    A lock parser that does not strip extras reports every extras-bearing
    direct requirement as "missing from lock" — six of them in this repo.
    """
    (tmp_path / "requirements.in").write_text("httpx[http2]>=0.28.1\nPyJWT>=2.13.0\n")
    (tmp_path / "requirements.lock").write_text("httpx[http2]==0.28.1\npyjwt[crypto]==2.13.0\n")
    parsed_in = guard.parse_requirements(tmp_path / "requirements.in")
    parsed_lock = guard.parse_requirements(tmp_path / "requirements.lock")
    assert set(parsed_in) == {"httpx", "pyjwt"} == set(parsed_lock)


# ---------------------------------------------------------------------------
# End-to-end guard behaviour
# ---------------------------------------------------------------------------


def test_clean_tree_passes(tmp_path):
    root = _fake_repo(
        tmp_path,
        "fastapi>=0.141.1\npydantic>=2.13.4,<3\n",
        "fastapi==0.141.1 \\\n    --hash=sha256:abc\npydantic==2.13.4 \\\n    --hash=sha256:def\n",
    )
    assert _load_guard(root).main() == 0


def test_pin_below_declared_floor_fails(tmp_path, capsys):
    root = _fake_repo(
        tmp_path,
        "fastapi>=0.141.1\n",
        "fastapi==0.140.0 \\\n    --hash=sha256:abc\n",
    )
    assert _load_guard(root).main() == 1
    assert ">=0.141.1" in capsys.readouterr().out


def test_pin_above_declared_cap_fails(tmp_path, capsys):
    root = _fake_repo(
        tmp_path,
        "pydantic>=2.13.4,<3\n",
        "pydantic==3.0.0 \\\n    --hash=sha256:abc\n",
    )
    assert _load_guard(root).main() == 1
    assert "<3" in capsys.readouterr().out


def test_direct_requirement_missing_from_lock_fails(tmp_path, capsys):
    root = _fake_repo(tmp_path, "fastapi>=0.141.1\nalembic>=1.19.1\n", "fastapi==0.141.1\n")
    assert _load_guard(root).main() == 1
    assert "alembic" in capsys.readouterr().out


def test_extras_bearing_requirement_is_still_compared(tmp_path):
    """An extras-bearing requirement must be compared, not skipped as missing."""
    ok_root = tmp_path / "ok"
    ok_root.mkdir()
    _fake_repo(ok_root, "uvicorn[standard]>=0.52.3\n", "uvicorn[standard]==0.52.4\n")
    assert _load_guard(ok_root).main() == 0

    bad_root = tmp_path / "bad"
    bad_root.mkdir()
    _fake_repo(bad_root, "uvicorn[standard]>=0.52.3\n", "uvicorn[standard]==0.52.2\n")
    assert _load_guard(bad_root).main() == 1


def test_empty_requirements_in_is_fatal(tmp_path, capsys):
    """The exact #2936 failure mode: no parseable inputs must NOT be green."""
    root = _fake_repo(tmp_path, "# all deps moved elsewhere\n", "fastapi==0.141.1\n")
    assert _load_guard(root).main() == 1
    assert "ZERO" in capsys.readouterr().out


def test_missing_requirements_in_is_fatal(tmp_path, capsys):
    (tmp_path / "requirements.lock").write_text("fastapi==0.141.1\n")
    assert _load_guard(tmp_path).main() == 1
    assert "not found" in capsys.readouterr().out


def test_lock_with_no_pins_is_fatal(tmp_path, capsys):
    root = _fake_repo(tmp_path, "fastapi>=0.141.1\n", "# no pins here\n")
    assert _load_guard(root).main() == 1
    assert "ZERO" in capsys.readouterr().out


def test_real_repo_is_clean():
    """The committed requirements.in / requirements.lock must agree."""
    assert _load_guard(_REPO_ROOT).main() == 0
