"""Build identity for the RegEngine backend.

The backend had none. `/`, `/health` and `/readiness` all answered without
saying which commit was answering, and `server/main.py` hard-coded
`version="1.0.0"`. That makes an entire class of failure structurally
undetectable: a rollout that fails its healthcheck reverts under
`restartPolicyType = "ON_FAILURE"` while the deploy workflow has already gone
green, and every probe afterwards asserts behaviour a months-old image
satisfies perfectly. The August 2026 Inflow Lab drift was only diagnosable
because that service publishes `commit_sha` — this ports the same idea.

`commit_source` is deliberately part of the payload. Knowing the SHA is half
the answer; knowing *where it came from* is what distinguishes "the platform
told us" from "we read a .git directory that happened to be in the image",
which is precisely the confusion that made the original drift take three days
to pin down.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

APP_VERSION = "1.0.0"
SHA_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")

# Ordered by trust. An explicitly-set REGENGINE_BUILD_SHA beats the platform's
# own value because it is the one a deploy pipeline can guarantee matches what
# it just shipped; the platform vars are the fallback when nothing set it.
COMMIT_SHA_ENV_VARS = (
    "REGENGINE_BUILD_SHA",
    "RAILWAY_GIT_COMMIT_SHA",
    "GITHUB_SHA",
    "SOURCE_VERSION",
    "COMMIT_SHA",
    "GIT_COMMIT",
)
BRANCH_ENV_VARS = (
    "REGENGINE_BUILD_BRANCH",
    "RAILWAY_GIT_BRANCH",
    "GITHUB_REF_NAME",
    "SOURCE_BRANCH",
    "BRANCH_NAME",
    "GIT_BRANCH",
)
DEPLOYMENT_ID_ENV_VARS = (
    "REGENGINE_DEPLOYMENT_ID",
    "RAILWAY_DEPLOYMENT_ID",
)


@dataclass(frozen=True)
class BuildInfo:
    version: str
    commit_sha: str | None = None
    commit_sha_short: str | None = None
    commit_source: str | None = None
    branch: str | None = None
    branch_source: str | None = None
    deployment_id: str | None = None
    deployment_source: str | None = None

    def public_dict(self) -> dict[str, str | None]:
        return {
            "version": self.version,
            "commit_sha": self.commit_sha,
            "commit_sha_short": self.commit_sha_short,
            "commit_source": self.commit_source,
            "branch": self.branch,
            "branch_source": self.branch_source,
            "deployment_id": self.deployment_id,
            "deployment_source": self.deployment_source,
        }


def current_build_info() -> BuildInfo:
    commit_sha, commit_source = _first_env(COMMIT_SHA_ENV_VARS)
    branch, branch_source = _first_env(BRANCH_ENV_VARS)

    # A value that is not a SHA is worse than no value: it looks like an
    # answer. Drop it and fall through to the local git read.
    if commit_sha and not _looks_like_sha(commit_sha):
        commit_sha = None
        commit_source = None
    if commit_sha is None:
        # The image has no .git — .dockerignore excludes it — so a stamp file
        # written into the build context by the deploy pipeline is what carries
        # identity into production. Local development still falls through to
        # reading .git directly.
        commit_sha = _stamped_sha()
        commit_source = "build_stamp" if commit_sha else None
    if commit_sha is None:
        commit_sha = _git_commit_sha()
        commit_source = "local_git" if commit_sha else None
    if branch is None:
        branch = _git_branch()
        branch_source = "local_git" if branch else None

    deployment_id, deployment_source = _first_env(DEPLOYMENT_ID_ENV_VARS)
    return BuildInfo(
        version=_env_text("REGENGINE_APP_VERSION") or APP_VERSION,
        commit_sha=commit_sha,
        commit_sha_short=commit_sha[:7] if commit_sha else None,
        commit_source=commit_source,
        branch=branch,
        branch_source=branch_source,
        deployment_id=deployment_id,
        deployment_source=deployment_source,
    )


def _first_env(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in names:
        value = _env_text(name)
        if value:
            return value, name
    return None, None


def _env_text(name: str) -> str | None:
    value = os.getenv(name)
    if value and value.strip():
        return value.strip()
    return None


BUILD_STAMP_PATH = "/app/build-sha.txt"


def _stamped_sha() -> str | None:
    """Read the SHA stamped into the image at build time, if present.

    Absent in development and in any image built before this existed, which is
    why it degrades to None rather than raising — a missing stamp must read as
    "unknown", never as a wrong answer.
    """
    stamp = _env_text("REGENGINE_BUILD_STAMP_PATH") or BUILD_STAMP_PATH
    return _normalize_sha(_read_text(Path(stamp)))


def _git_commit_sha() -> str | None:
    """Read HEAD without shelling out to git, which is absent from the image."""
    git_dir = _git_dir()
    if git_dir is None:
        return None

    head = _read_text(git_dir / "HEAD")
    if not head:
        return None
    if head.startswith("ref: "):
        return _normalize_sha(_read_text(git_dir / head.removeprefix("ref: ").strip()))
    return _normalize_sha(head)


def _git_branch() -> str | None:
    git_dir = _git_dir()
    if git_dir is None:
        return None

    head = _read_text(git_dir / "HEAD")
    if not head or not head.startswith("ref: refs/heads/"):
        return None
    return head.removeprefix("ref: refs/heads/").strip()


def _git_dir() -> Path | None:
    repo_root = Path(__file__).resolve().parents[2]
    git_path = repo_root / ".git"
    if git_path.is_dir():
        return git_path
    if git_path.is_file():
        gitdir_line = _read_text(git_path)
        if gitdir_line and gitdir_line.startswith("gitdir: "):
            resolved = (repo_root / gitdir_line.removeprefix("gitdir: ").strip()).resolve()
            if resolved.is_dir():
                return resolved
    return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _normalize_sha(value: str | None) -> str | None:
    if value and _looks_like_sha(value):
        return value
    return None


def _looks_like_sha(value: str) -> bool:
    return bool(SHA_RE.fullmatch(value.strip()))
