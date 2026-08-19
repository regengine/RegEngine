"""Build identity must be honest about what it knows and where it learned it.

The backend previously published no commit at all, which made an entire class
of failure undetectable: a rollout that fails its healthcheck reverts under
``railway.toml``'s ``restartPolicyType = "ON_FAILURE"`` after the deploy
workflow has already gone green, and every probe afterwards asserts behaviour
an old image satisfies perfectly.

The property that matters most here is not "reports a SHA" but "never reports
a wrong one". A confident wrong answer is worse than a missing one, because
the post-deploy check in ``deploy.yml`` compares this value against
``github.sha`` and would pass on a lie.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.build_info import current_build_info  # noqa: E402

# Full-length git object ids, not credentials. They are 40 hex characters
# because that is what the code under test parses — `_looks_like_sha` accepts
# 7 to 64, and a short fixture would not exercise the real shape. detect-secrets
# scores any long hex run as high entropy, so the false positive is marked
# rather than dodged by splicing the literals into pieces, which would only
# hide them from the scanner and from the next reader too.
SHA = "1234567890abcdef1234567890abcdef12345678"  # pragma: allowlist secret — fake commit id
OTHER_SHA = "fedcba0987654321fedcba0987654321fedcba09"  # pragma: allowlist secret — fake commit id

ALL_SOURCES = (
    "REGENGINE_BUILD_SHA",
    "RAILWAY_GIT_COMMIT_SHA",
    "GITHUB_SHA",
    "SOURCE_VERSION",
    "COMMIT_SHA",
    "GIT_COMMIT",
    "REGENGINE_BUILD_BRANCH",
    "RAILWAY_GIT_BRANCH",
    "GITHUB_REF_NAME",
    "SOURCE_BRANCH",
    "BRANCH_NAME",
    "GIT_BRANCH",
    "REGENGINE_DEPLOYMENT_ID",
    "RAILWAY_DEPLOYMENT_ID",
    "REGENGINE_APP_VERSION",
)


@pytest.fixture()
def clean_env(monkeypatch, tmp_path):
    """Reproduce the deployed image: no env identity, no stamp, and no .git.

    Two things would otherwise make these tests lie about production. GitHub
    Actions sets GITHUB_SHA, so the suite would pass or fail depending on
    where it ran. And a developer checkout has a .git directory, so the local
    fallback finds a real commit and every "reports nothing" assertion
    silently becomes "reports the working tree" — the fallback is correct
    behaviour in development and exactly what the image does not have
    (.dockerignore excludes .git).
    """
    import shared.build_info as build_info

    for name in ALL_SOURCES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REGENGINE_BUILD_STAMP_PATH", str(tmp_path / "absent.txt"))
    monkeypatch.setattr(build_info, "_git_dir", lambda: None)
    return tmp_path


def test_explicit_build_sha_wins_over_platform_and_stamp(clean_env, monkeypatch):
    """What the pipeline set beats what the platform guessed.

    The deploy workflow stamps the commit it is actually shipping; a platform
    variable can describe a different one (a re-run, a manual redeploy).
    """
    stamp = clean_env / "stamp.txt"
    stamp.write_text(OTHER_SHA, encoding="utf-8")
    monkeypatch.setenv("REGENGINE_BUILD_STAMP_PATH", str(stamp))
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", OTHER_SHA)
    monkeypatch.setenv("REGENGINE_BUILD_SHA", SHA)

    info = current_build_info()

    assert info.commit_sha == SHA
    assert info.commit_source == "REGENGINE_BUILD_SHA"
    assert info.commit_sha_short == SHA[:7]


def test_build_stamp_is_read_when_no_env_var_is_set(clean_env, monkeypatch):
    """The image has no .git, so the stamp file is how identity ships."""
    stamp = clean_env / "stamp.txt"
    stamp.write_text(f"{SHA}\n", encoding="utf-8")
    monkeypatch.setenv("REGENGINE_BUILD_STAMP_PATH", str(stamp))

    info = current_build_info()

    assert info.commit_sha == SHA
    assert info.commit_source == "build_stamp"


def test_placeholder_stamp_reads_as_absent_not_as_a_commit(clean_env, monkeypatch):
    """The committed placeholder is the literal string "unknown".

    It exists so `COPY build-sha.txt` always succeeds. It must never be
    mistaken for a commit — a committed real SHA would go stale and lie, which
    is the whole failure this module exists to prevent.
    """
    stamp = clean_env / "stamp.txt"
    stamp.write_text("unknown\n", encoding="utf-8")
    monkeypatch.setenv("REGENGINE_BUILD_STAMP_PATH", str(stamp))

    info = current_build_info()

    assert info.commit_sha is None
    assert info.commit_source is None


def test_non_sha_env_value_is_discarded_rather_than_reported(clean_env, monkeypatch):
    """A value that is not a SHA looks like an answer. It must not be one."""
    monkeypatch.setenv("REGENGINE_BUILD_SHA", "refs/heads/main")

    info = current_build_info()

    assert info.commit_sha is None
    assert info.commit_source is None


def test_missing_identity_is_null_everywhere_and_never_raises(clean_env):
    """Health endpoints embed this. It degrades; it does not throw."""
    info = current_build_info()
    payload = info.public_dict()

    assert payload["commit_sha"] is None
    assert payload["commit_sha_short"] is None
    assert payload["commit_source"] is None
    assert payload["version"]


def test_public_dict_reports_where_each_value_came_from(clean_env, monkeypatch):
    """``commit_source`` is what distinguishes a trustworthy SHA from a guess.

    Knowing the SHA is half the answer; the August 2026 drift took three days
    partly because nobody could tell whether a value came from the platform or
    from a .git directory that happened to be lying around.
    """
    monkeypatch.setenv("REGENGINE_BUILD_SHA", SHA)
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "main")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-abc123")
    monkeypatch.setenv("REGENGINE_APP_VERSION", "2.5.0")

    payload = current_build_info().public_dict()

    assert payload == {
        "version": "2.5.0",
        "commit_sha": SHA,
        "commit_sha_short": SHA[:7],
        "commit_source": "REGENGINE_BUILD_SHA",
        "branch": "main",
        "branch_source": "RAILWAY_GIT_BRANCH",
        "deployment_id": "dep-abc123",
        "deployment_source": "RAILWAY_DEPLOYMENT_ID",
    }


def test_unreadable_stamp_file_degrades_to_absent(clean_env, monkeypatch):
    """A directory where a file was expected must not crash the health probe."""
    directory = clean_env / "not-a-file"
    directory.mkdir()
    monkeypatch.setenv("REGENGINE_BUILD_STAMP_PATH", str(directory))

    info = current_build_info()

    assert info.commit_sha is None
