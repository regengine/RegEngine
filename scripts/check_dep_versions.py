#!/usr/bin/env python3
"""CI guard — reject per-service requirements files that drift below pyproject.toml floors.

Scans all ``services/*/requirements*.txt`` files and compares every package
that also appears in ``[tool.poetry.dependencies]`` against the canonical
minimum version declared there.  A service file is allowed to raise the floor
(e.g. >=2.8.0 when pyproject says >=2.7.0) but MUST NOT lower it.

Hard-pinned ``==X.Y.Z`` specs in service files are also checked: the pinned
version must be >= the canonical minimum.

Exit code 0 = clean.  Non-zero = drift detected.

Usage:
    python scripts/check_dep_versions.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent

# Packages whose version floors must not regress in per-service files.
# Extend this list as new shared dependencies are added to pyproject.toml.
GUARDED_PACKAGES = {
    "pydantic",
    "pydantic-settings",
    "fastapi",
    "sqlalchemy",
    "uvicorn",
    "httpx",
    "alembic",
}

# Regex to extract a minimum version from a PEP 440 constraint string.
# Handles: >=X, ==X, ~=X.  Ignores upper-bound-only specs (<X, <=X).
_VER_RE = re.compile(r"(>=|==|~=)\s*([\d]+(?:\.[\d]+)*)")

# Requirement-line parser: "package-name[extras] spec  # comment"
_REQ_RE = re.compile(
    r"^\s*(?P<pkg>[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)"  # package name
    r"(?:\[.*?\])?"                                              # optional extras
    r"(?P<spec>[^#\n]*)",                                        # version spec
)


def _parse_version(v: str) -> tuple[int, ...]:
    """Convert '2.7.0' → (2, 7, 0)."""
    return tuple(int(x) for x in v.split(".") if x.isdigit())


def load_canonical_floors(pyproject: Path) -> dict[str, tuple[int, ...]]:
    """Return {normalised-package-name: min_version_tuple} from pyproject.toml."""
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)

    deps: dict[str, str] = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    floors: dict[str, tuple[int, ...]] = {}
    for pkg, spec in deps.items():
        pkg_norm = pkg.lower().replace("_", "-")
        if pkg_norm not in GUARDED_PACKAGES:
            continue
        # spec can be a string like ">=2.7.0" or a dict like {"version": ">=2.7.0", ...}
        spec_str: str = spec if isinstance(spec, str) else spec.get("version", "")
        match = _VER_RE.search(spec_str)
        if match:
            floors[pkg_norm] = _parse_version(match.group(2))
    return floors


def iter_service_req_files() -> list[Path]:
    services_dir = REPO_ROOT / "services"
    return sorted(services_dir.glob("*/requirements*.txt"))


def check_file(path: Path, floors: dict[str, tuple[int, ...]]) -> list[str]:
    """Return violation strings for any guarded package that dips below its floor."""
    violations: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return [f"could not read: {exc}"]

    for lineno, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _REQ_RE.match(line)
        if not m:
            continue
        pkg_norm = m.group("pkg").lower().replace("_", "-")
        if pkg_norm not in floors:
            continue
        spec_str = m.group("spec").strip()
        floor = floors[pkg_norm]

        ver_matches = _VER_RE.findall(spec_str)
        if not ver_matches:
            # No version constraint — nothing to check against.
            continue

        for op, ver_str in ver_matches:
            pinned = _parse_version(ver_str)
            if pinned < floor:
                violations.append(
                    f"  L{lineno}: {pkg_norm}{spec_str!r} — "
                    f"floor {'.'.join(str(x) for x in pinned)} is below "
                    f"canonical minimum {'.'.join(str(x) for x in floor)} "
                    f"(pyproject.toml)"
                )
    return violations


def main() -> int:
    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.is_file():
        print(f"ERROR: {pyproject} not found — cannot determine canonical floors.")
        return 1

    floors = load_canonical_floors(pyproject)
    if not floors:
        print("WARNING: No guarded packages found in pyproject.toml — nothing to check.")
        return 0

    req_files = iter_service_req_files()
    if not req_files:
        print("No services/*/requirements*.txt files found — nothing to check.")
        return 0

    any_violations = False
    for path in req_files:
        rel = path.relative_to(REPO_ROOT)
        violations = check_file(path, floors)
        if violations:
            any_violations = True
            print(f"\nFAIL {rel}")
            for v in violations:
                print(v)
        else:
            print(f"  OK  {rel}")

    print(f"\nCanonical floors from pyproject.toml:")
    for pkg, ver in sorted(floors.items()):
        print(f"  {pkg}: >={'.'.join(str(x) for x in ver)}")

    if any_violations:
        print(
            "\nVersion drift detected in per-service requirements file(s).\n"
            "Per-service files MUST NOT lower the floor set by pyproject.toml.\n"
            "Either raise the floor in the service file or update pyproject.toml\n"
            "if the platform-wide minimum is intentionally changing.\n"
            "See issue #1886."
        )
        return 1

    print("\nOK — no version drift in per-service requirements files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
