"""The production lock carries no test tooling; the dev lock is constrained by it (WI-06)."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
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


def test_dev_and_experimental_specs_are_constrained_by_the_production_lock():
    for spec in ("requirements-dev.in", "requirements-experimental.in"):
        first_directive = next(
            line.strip()
            for line in (_REPO_ROOT / spec).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
        assert first_directive == "-c requirements.lock", spec


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
