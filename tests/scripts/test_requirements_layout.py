"""The production lock carries no test tooling; the dev and experimental locks are constrained by it (WI-06).

The constraint is a pip-compile command-line flag, never a ``-c`` line in a
``.in`` file: Dependabot cannot open a constraint file it did not fetch.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CONSTRAINT_FLAG = "--constraint=requirements.lock"
# pip requirements-file spellings of "read this other file": -c / -r (value
# attached or separated) and --constraint / --requirement (space or "=").
_FILE_REFERENCE = re.compile(r"^(?:-[cr]\s*|--(?:constraint|requirement)(?:\s+|=))(?P<path>\S+)")
_DEV_OR_EXPERIMENTAL_SPEC = re.compile(r"requirements-(?:dev|experimental|\$\{name\})\.in")
_DEV_ONLY = (
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "pytest-mock",
    "pytest-xdist",
    "hypothesis",
    "aiosqlite",
    "testcontainers",
)
_EXPERIMENTAL_ONLY = ("pyzbar",)


def _pinned(lock: Path) -> set[str]:
    return {m.group(1).lower() for m in re.finditer(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==", lock.read_text(), re.M)}


def _declared(spec: Path) -> set[str]:
    names = set()
    for line in spec.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            names.add(re.split(r"[\[<>=!~ ]", line, 1)[0].lower())
    return names


def test_production_spec_and_lock_carry_no_test_tooling():
    declared = _declared(_REPO_ROOT / "requirements.in")
    pinned = _pinned(_REPO_ROOT / "requirements.lock")
    for name in _DEV_ONLY + _EXPERIMENTAL_ONLY:
        assert name not in declared, f"{name} belongs in requirements-dev.in or requirements-experimental.in"
        assert name not in pinned, f"{name} is pinned in requirements.lock; recompile it from requirements.in"


def _file_references(text: str) -> list[tuple[int, str]]:
    """(line number, path) for every -c/-r directive in a requirements file."""
    found = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        match = _FILE_REFERENCE.match(raw.strip())
        if match:
            found.append((lineno, match.group("path").strip("\"'")))
    return found


def test_file_reference_detection_covers_the_pip_spellings():
    text = "\n".join(
        [
            "# -c commented.lock",
            "-c requirements.lock",
            "-rbase.in",
            "--constraint=pins.txt  # trailing comment",
            '--requirement "other.in"',
            "--require-hashes",
            "pytest>=9.1.1",
        ]
    )
    assert _file_references(text) == [(2, "requirements.lock"), (3, "base.in"), (4, "pins.txt"), (5, "other.in")]


def test_root_specs_reference_only_files_dependabot_fetches():
    specs = sorted(_REPO_ROOT.glob("requirements*.in"))
    assert {"requirements.in", "requirements-dev.in", "requirements-experimental.in"} <= {s.name for s in specs}
    for spec in specs:
        for lineno, path in _file_references(spec.read_text()):
            assert path.endswith((".txt", ".in")), (
                f"{spec.name}:{lineno} references {path!r}. Dependabot fetches a -c/-r target only when its "
                "name ends in .txt or .in; pip then cannot open the missing file and the weekly pip run for "
                "directory '/' fails with dependency_file_not_evaluatable, so no root requirement is updated. "
                f"Pass requirements.lock to pip-compile as {_CONSTRAINT_FLAG} instead (CONTRIBUTING.md)."
            )


def test_dev_and_experimental_lock_headers_record_the_production_constraint():
    for name in ("dev", "experimental"):
        lock = _REPO_ROOT / f"requirements-{name}.lock"
        recorded = [
            line.lstrip("# ")
            for line in lock.read_text().splitlines()[:10]
            if line.startswith("#") and line.lstrip("# ").startswith("pip-compile ")
        ]
        assert len(recorded) == 1, f"{lock.name}: expected one recorded compile command, found {recorded}"
        assert _CONSTRAINT_FLAG in recorded[0].split(), (
            f"{lock.name} was compiled without {_CONSTRAINT_FLAG}: {recorded[0]}"
        )


def test_ci_compiles_the_dev_and_experimental_locks_with_the_production_constraint():
    for workflow in ("backend-ci.yml", "dependabot-lock-sync.yml"):
        commands = [
            line.strip()
            for line in (_REPO_ROOT / ".github" / "workflows" / workflow).read_text().splitlines()
            if "pip-compile " in line and _DEV_OR_EXPERIMENTAL_SPEC.search(line)
        ]
        recorded = [c for c in commands if c.startswith("CUSTOM_COMPILE_COMMAND=")]
        invoked = [c for c in commands if c.startswith("pip-compile ")]
        assert recorded, f"{workflow}: no one-line CUSTOM_COMPILE_COMMAND naming a dev/experimental .in file"
        assert invoked, f"{workflow}: no one-line pip-compile invocation naming a dev/experimental .in file"
        for command in commands:
            assert _CONSTRAINT_FLAG in command, f"{workflow} compiles without {_CONSTRAINT_FLAG}: {command}"


def test_dev_lock_pins_every_dev_package_and_shares_versions_with_production():
    dev_pinned = {
        m.group(1).lower(): m.group(2)
        for m in re.finditer(
            r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([^\s\\]+)", (_REPO_ROOT / "requirements-dev.lock").read_text(), re.M
        )
    }
    for name in _DEV_ONLY:
        assert name in dev_pinned, name
    prod_pinned = {
        m.group(1).lower(): m.group(2)
        for m in re.finditer(
            r"^([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([^\s\\]+)", (_REPO_ROOT / "requirements.lock").read_text(), re.M
        )
    }
    shared = set(dev_pinned) & set(prod_pinned)
    assert shared, "the dev lock should share at least its transitive HTTP/packaging deps with production"
    diverged = {n: (prod_pinned[n], dev_pinned[n]) for n in shared if prod_pinned[n] != dev_pinned[n]}
    assert diverged == {}, f"dev lock diverges from the production constraint: {diverged}"
