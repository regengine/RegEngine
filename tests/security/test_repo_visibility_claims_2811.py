"""The README must not claim this repository is public while confidential
business material is tracked in it — #2811.

Neither fact is a defect on its own:

* Tracked fundraising material in a **private** repository is scope debt
  (`REPO_PURPOSE.md`), not disclosure.
* A README describing a genuinely public repository is simply accurate.

The defect is the **combination**, and specifically the direction it fails in.
`README.md` stated "The repository is public for transparency and audit" as
settled fact, paired with a coherent rationale (the `/proof` and `/verify`
surfaces, which are real). The repository was private. Someone trusting the
README could close that gap the wrong way — flipping visibility without
re-auditing the tree — and disclose the material in that instant, with no
separate review step to catch it.

These tests make that combination impossible to reach silently. They do **not**
require the confidential files to be removed: that is a business decision about
this repository's intended visibility, taken by its owner, and either answer is
legitimate. What the tests require is that the README and the tree cannot
disagree in the dangerous direction.

The authoritative list of confidential paths lives in
`docs/security/PRE_PUBLIC_CHECKLIST.md` rather than here, so that the operator
reading the checklist before flipping visibility and the test enforcing it can
never drift apart.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_README = _REPO_ROOT / "README.md"
_CHECKLIST = _REPO_ROOT / "docs" / "security" / "PRE_PUBLIC_CHECKLIST.md"

# Phrasings that assert the repository itself is public. Deliberately narrow:
# "public proof surface", "public verifier tools" and "public samples" all
# describe published *artifacts*, not repository visibility, and must not match.
_CLAIMS_PUBLIC = re.compile(
    r"\b(?:this\s+)?repo(?:sitory)?\s+is\s+public\b"
    r"|\bpublic\s+repo(?:sitory)?\b"
    r"|\brepo(?:sitory)?\s+is\s+(?:now\s+)?open[- ]source\b",
    re.IGNORECASE,
)

_FENCE = re.compile(r"```confidential-paths\n(.*?)```", re.DOTALL)


def _confidential_paths() -> list[str]:
    match = _FENCE.search(_CHECKLIST.read_text(encoding="utf-8"))
    assert match, (
        f"{_CHECKLIST.relative_to(_REPO_ROOT)} has no ```confidential-paths``` block. "
        f"That block is the authoritative list these tests enforce; without it they "
        f"would pass while checking nothing."
    )
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def _tracked(path: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


_CONFIDENTIAL = _confidential_paths()


def test_checklist_lists_paths():
    """Guard the guard: an empty list would make every check below vacuous."""
    assert _CONFIDENTIAL, (
        "The ```confidential-paths``` block in PRE_PUBLIC_CHECKLIST.md is empty. If the "
        "material really was removed, delete these tests deliberately rather than "
        "leaving them passing on an empty set."
    )


def test_readme_does_not_claim_the_repository_is_public_while_material_is_tracked():
    """The #2811 combination itself."""
    readme = _README.read_text(encoding="utf-8")
    claims = [m.group(0) for m in _CLAIMS_PUBLIC.finditer(readme)]
    if not claims:
        return  # README makes no public-repository claim; nothing to reconcile

    still_tracked = [p for p in _CONFIDENTIAL if _tracked(p)]
    assert not still_tracked, (
        f"README.md asserts the repository is public ({claims!r}) while "
        f"{len(still_tracked)} confidential path(s) from "
        f"{_CHECKLIST.relative_to(_REPO_ROOT)} are still tracked:\n  "
        + "\n  ".join(still_tracked)
        + "\n\nResolve in one of two directions — correct the README, or complete "
        "the checklist (relocate the files AND purge them from history; `git rm` "
        "leaves every prior revision readable). Do not silence this test (#2811)."
    )


def test_readme_points_at_the_pre_public_checklist():
    """The gate is only useful if the front page routes people to it."""
    readme = _README.read_text(encoding="utf-8")
    assert "docs/security/PRE_PUBLIC_CHECKLIST.md" in readme, (
        "README.md no longer links docs/security/PRE_PUBLIC_CHECKLIST.md. Someone "
        "deciding to flip this repository public reads the README, not the security "
        "directory (#2811)."
    )


def test_checklist_exists_and_states_the_history_caveat():
    """`git rm` at HEAD is the trap this checklist exists to prevent."""
    text = _CHECKLIST.read_text(encoding="utf-8")
    assert "history" in text.lower(), (
        "PRE_PUBLIC_CHECKLIST.md must state that removing files at HEAD does not "
        "remove them from history — that is the failure mode it exists to prevent."
    )


@pytest.mark.parametrize("path", _CONFIDENTIAL)
def test_checklist_entries_are_tracked_or_explicitly_quarantined(path: str):
    """Removed HEAD files remain on the historical disclosure checklist.

    Require an explicit ignore rule when a path no longer exists, so the
    checklist still prevents accidental recommits after relocation.
    """
    ignored = (
        subprocess.run(
            ["git", "check-ignore", "--no-index", "--", path],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )
    assert _tracked(path) or (_REPO_ROOT / path).exists() or ignored, (
        f"{_CHECKLIST.relative_to(_REPO_ROOT)} lists {path!r}, which is neither "
        "tracked, present, nor quarantined by an ignore rule."
    )
