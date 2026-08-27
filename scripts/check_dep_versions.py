#!/usr/bin/env python3
"""CI guard — reject dependency version drift between the declared floors and the lock.

``requirements.in`` is the human-edited single source of truth for what
RegEngine depends on (``pyproject.toml`` says so verbatim, and declares no
dependencies of its own).  ``requirements.lock`` is its pip-compile output
and the only thing Docker and CI ever install.  Those two files can drift:
a hand-edited lock, a bad merge, or a cherry-picked revert can leave the
lock pinning a version that does not satisfy the floor (or the cap) the
``.in`` file declares — and because installs read only the lock, nothing
else in the repo notices.

This guard asserts, for every direct requirement in ``requirements.in``:

* it has a pin in ``requirements.lock`` (a direct dep missing from the lock
  is never installed), and
* that pin satisfies the ``.in`` specifier — floor *and* cap.

It additionally re-checks any ``services/*/requirements*.txt`` file that
still exists against the same floors.  Those files were deprecated in
#1429; if one comes back it must not lower a floor.

History (#2936): this script used to read ``[tool.poetry.dependencies]``
from ``pyproject.toml``.  That table has never existed — ``pyproject.toml``
states in a comment that dependencies are deliberately *not* declared there
— so ``load_canonical_floors`` always returned ``{}``, the guard printed a
WARNING, returned 0 before opening a single requirements file, and the
"Dep version drift guard" hard gate in backend-ci.yml passed on every PR
while checking nothing.  Empty inputs are now fatal rather than green: a
guard with no inputs is not a guard.

Exit code 0 = clean.  Non-zero = drift detected, or the guard has no
inputs to check.

Usage:
    python scripts/check_dep_versions.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIREMENTS_IN = REPO_ROOT / "requirements.in"
REQUIREMENTS_LOCK = REPO_ROOT / "requirements.lock"

# ---------------------------------------------------------------------------
# Minimal PEP 440 version + specifier handling.
#
# Deliberately dependency-free: the ``dep-version-check`` job in
# backend-ci.yml runs this script straight after actions/setup-python with
# no ``pip install`` step, so ``packaging`` is not importable there.  The
# subset below covers epoch/release/pre/post/dev and the operators that
# appear in requirements files (>=, >, <=, <, ==, ===, !=, ~=), including
# ``.*`` wildcards on == and !=.
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(
    r"^\s*v?"
    r"(?:(?P<epoch>\d+)!)?"
    r"(?P<release>\d+(?:\.\d+)*)"
    r"(?P<pre>[-_.]?(?:a|b|c|rc|alpha|beta|pre|preview)[-_.]?\d*)?"
    r"(?P<post>[-_.]?(?:post|rev|r)[-_.]?\d*|-\d+)?"
    r"(?P<dev>[-_.]?dev[-_.]?\d*)?"
    r"(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?"
    r"\s*$",
    re.IGNORECASE,
)

_PRE_NORM = {"alpha": "a", "beta": "b", "c": "rc", "pre": "rc", "preview": "rc"}


class InvalidVersion(ValueError):
    """Raised when a version string cannot be parsed."""


class Version:
    """Comparable PEP 440 version (subset — see module note)."""

    __slots__ = ("raw", "_key")

    def __init__(self, raw: str) -> None:
        m = _VERSION_RE.match(raw)
        if not m:
            raise InvalidVersion(raw)
        self.raw = raw.strip()

        epoch = int(m.group("epoch") or 0)
        release = tuple(int(p) for p in m.group("release").split("."))

        pre = m.group("pre")
        if pre:
            pm = re.match(r"[-_.]?([a-z]+)[-_.]?(\d*)$", pre, re.IGNORECASE)
            letter = pm.group(1).lower()
            letter = _PRE_NORM.get(letter, letter)
            pre_key: tuple = (letter, int(pm.group(2) or 0))
        else:
            # No pre-release sorts AFTER any pre-release of the same release.
            pre_key = ("zzz", 0)

        post = m.group("post")
        if post:
            pm = re.search(r"(\d+)$", post)
            post_key = int(pm.group(1)) if pm else 0
        else:
            post_key = -1

        dev = m.group("dev")
        if dev:
            pm = re.search(r"(\d+)$", dev)
            dev_key = int(pm.group(1)) if pm else 0
        else:
            # No dev segment sorts AFTER any dev release.
            dev_key = 1 << 30

        self._key = (epoch, release, pre_key, post_key, dev_key)

    def _cmp_key(self, other: "Version") -> tuple[tuple, tuple]:
        """Right-pad the release tuples so 2.0 and 2.0.0 compare equal."""
        a, b = self._key, other._key
        width = max(len(a[1]), len(b[1]))

        def pad(release: tuple) -> tuple:
            return tuple(release) + (0,) * (width - len(release))

        return ((a[0], pad(a[1]), *a[2:]), (b[0], pad(b[1]), *b[2:]))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        a, b = self._cmp_key(other)
        return a == b

    def __lt__(self, other: "Version") -> bool:
        a, b = self._cmp_key(other)
        return a < b

    def __le__(self, other: "Version") -> bool:
        return self == other or self < other

    def __gt__(self, other: "Version") -> bool:
        return not self <= other

    def __ge__(self, other: "Version") -> bool:
        return not self < other

    def __hash__(self) -> int:
        return hash(self._key)

    def __str__(self) -> str:
        return self.raw


_SPEC_RE = re.compile(r"(===|==|!=|~=|>=|<=|>|<)\s*([^,;\s]+)")


def _release_prefix_match(pin: Version, prefix: str) -> bool:
    """``==2.7.*`` style comparison."""
    want = tuple(int(p) for p in prefix.split(".") if p.isdigit())
    got = tuple(pin._key[1][: len(want)])
    return got == want


def specifier_allows(spec: str, pin: Version) -> tuple[bool, str]:
    """Return (satisfied, first-failing-clause) for *spec* against *pin*."""
    clauses = _SPEC_RE.findall(spec or "")
    if not clauses:
        return True, ""
    for op, raw in clauses:
        wildcard = raw.endswith(".*")
        base = raw[:-2] if wildcard else raw
        if op == "===":
            ok = pin.raw == raw
        elif wildcard and op in ("==", "!="):
            hit = _release_prefix_match(pin, base)
            ok = hit if op == "==" else not hit
        else:
            try:
                other = Version(base)
            except InvalidVersion:
                # Unparseable bound — treat as unchecked rather than silently
                # passing the whole requirement.
                return False, f"{op}{raw} (unparseable version)"
            if op == "==":
                ok = pin == other
            elif op == "!=":
                ok = pin != other
            elif op == ">=":
                ok = pin >= other
            elif op == ">":
                ok = pin > other
            elif op == "<=":
                ok = pin <= other
            elif op == "<":
                ok = pin < other
            elif op == "~=":
                # ~=X.Y  ==  >=X.Y, ==X.*   /   ~=X.Y.Z == >=X.Y.Z, ==X.Y.*
                rel = other._key[1]
                if len(rel) < 2:
                    return False, f"~={raw} (needs at least two release segments)"
                prefix = ".".join(str(p) for p in rel[:-1])
                ok = pin >= other and _release_prefix_match(pin, prefix)
            else:  # pragma: no cover - _SPEC_RE cannot produce anything else
                ok = True
        if not ok:
            return False, f"{op}{raw}"
    return True, ""


# ---------------------------------------------------------------------------
# Requirement-file parsing
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"^\s*(?P<pkg>[A-Za-z0-9][A-Za-z0-9._-]*)\s*(?P<extras>\[[^\]]*\])?\s*(?P<spec>.*)$")


def normalise(pkg: str) -> str:
    """PEP 503 name normalisation: 'PyJWT' and 'py_jwt' -> 'pyjwt'."""
    return re.sub(r"[-_.]+", "-", pkg).lower()


def _logical_lines(path: Path):
    """Yield (lineno, text) with comments stripped and backslash joins applied."""
    buf = ""
    start = 0
    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not buf:
            start = lineno
        if line.endswith("\\"):
            buf += line[:-1]
            continue
        buf += line
        text = buf.strip()
        buf = ""
        if text:
            yield start, text
    if buf.strip():
        yield start, buf.strip()


def parse_requirements(path: Path) -> dict[str, tuple[str, int]]:
    """Return {normalised-name: (specifier, lineno)} for a requirements file.

    Environment markers (``; python_version < "3.12"``) are stripped — the
    guard compares version bounds, not marker applicability.  ``--hash=``
    continuation lines and pip options are skipped.
    """
    out: dict[str, tuple[str, int]] = {}
    for lineno, text in _logical_lines(path):
        if text.startswith("-"):  # -r / -c / --index-url / --hash
            continue
        text = text.split(";", 1)[0].strip()
        if not text:
            continue
        m = _NAME_RE.match(text)
        if not m:
            continue
        spec = m.group("spec").strip()
        # A bare URL / path requirement carries no comparable version.
        if spec.startswith("@"):
            continue
        out[normalise(m.group("pkg"))] = (spec, lineno)
    return out


def iter_service_req_files() -> list[Path]:
    services_dir = REPO_ROOT / "services"
    return sorted(services_dir.glob("*/requirements*.txt"))


def floors_from(specs: dict[str, tuple[str, int]]) -> dict[str, Version]:
    """Extract the lower bound (>=, ==, ~=) declared for each package."""
    floors: dict[str, Version] = {}
    for pkg, (spec, _lineno) in specs.items():
        for op, raw in _SPEC_RE.findall(spec):
            if op not in (">=", "==", "~=", "==="):
                continue
            try:
                v = Version(raw[:-2] if raw.endswith(".*") else raw)
            except InvalidVersion:
                continue
            if pkg not in floors or v > floors[pkg]:
                floors[pkg] = v
    return floors


def check_service_file(path: Path, floors: dict[str, Version]) -> list[str]:
    """Violations for any package whose service-file bound dips below the floor."""
    violations: list[str] = []
    try:
        specs = parse_requirements(path)
    except OSError as exc:
        return [f"could not read: {exc}"]

    for pkg, (spec, lineno) in specs.items():
        floor = floors.get(pkg)
        if floor is None:
            continue
        for op, raw in _SPEC_RE.findall(spec):
            if op not in (">=", "==", "~=", "==="):
                continue
            try:
                v = Version(raw[:-2] if raw.endswith(".*") else raw)
            except InvalidVersion:
                continue
            if v < floor:
                violations.append(
                    f"  L{lineno}: {pkg}{spec!r} — bound {v} is below the "
                    f"requirements.in floor {floor}"
                )
    return violations


def main() -> int:
    for required in (REQUIREMENTS_IN, REQUIREMENTS_LOCK):
        if not required.is_file():
            print(f"ERROR: {required.relative_to(REPO_ROOT)} not found — the guard has no inputs.")
            print("A dependency guard that cannot read its inputs is not checking anything.")
            return 1

    declared = parse_requirements(REQUIREMENTS_IN)
    pinned_specs = parse_requirements(REQUIREMENTS_LOCK)

    if not declared:
        print("ERROR: requirements.in declared ZERO parseable requirements.")
        print("The guard has no inputs — it is not checking anything. See #2936.")
        return 1
    if not pinned_specs:
        print("ERROR: requirements.lock contains ZERO parseable pins.")
        print("The guard has no inputs — it is not checking anything. See #2936.")
        return 1

    pins: dict[str, Version] = {}
    for pkg, (spec, _lineno) in pinned_specs.items():
        for op, raw in _SPEC_RE.findall(spec):
            if op in ("==", "==="):
                try:
                    pins[pkg] = Version(raw)
                except InvalidVersion:
                    pass
                break

    if not pins:
        print("ERROR: requirements.lock yielded ZERO '==' pins — it is not a lockfile.")
        return 1

    missing: list[str] = []
    drifted: list[str] = []
    checked = 0

    for pkg, (spec, lineno) in sorted(declared.items()):
        pin = pins.get(pkg)
        if pin is None:
            missing.append(f"  requirements.in:{lineno}: {pkg}{spec} — no '==' pin in requirements.lock")
            continue
        checked += 1
        ok, clause = specifier_allows(spec, pin)
        if not ok:
            drifted.append(
                f"  requirements.in:{lineno}: {pkg}{spec} — lock pins {pkg}=={pin}, "
                f"which violates {clause}"
            )

    print(f"requirements.in: {len(declared)} direct requirement(s)")
    print(f"requirements.lock: {len(pins)} pinned distribution(s)")
    print(f"Compared {checked} direct requirement(s) against their lock pin.")

    if checked == 0:
        print("\nERROR: zero requirements were actually compared — the guard is vacuous.")
        return 1

    service_files = iter_service_req_files()
    floors = floors_from(declared)
    service_violations = False
    if service_files:
        print("\nPer-service requirements files (deprecated — see #1429):")
        for path in service_files:
            rel = path.relative_to(REPO_ROOT)
            violations = check_service_file(path, floors)
            if violations:
                service_violations = True
                print(f"\nFAIL {rel}")
                for v in violations:
                    print(v)
            else:
                print(f"  OK  {rel}")

    if missing:
        print("\nDirect requirements with no pin in requirements.lock:")
        for m in missing:
            print(m)
    if drifted:
        print("\nLock pins that violate the requirements.in specifier:")
        for d in drifted:
            print(d)

    if missing or drifted or service_violations:
        print(
            "\nDependency version drift detected.\n"
            "requirements.in declares the floors and caps; requirements.lock is the\n"
            "only thing Docker and CI install. They must agree. Re-run\n"
            "  pip-compile --allow-unsafe --generate-hashes \\\n"
            "      --output-file=requirements.lock requirements.in\n"
            "rather than hand-editing the lock. See issues #1886 and #2936."
        )
        return 1

    print("\nOK — every direct requirement is pinned in requirements.lock within its declared bounds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
