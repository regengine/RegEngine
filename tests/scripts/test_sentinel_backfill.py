from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sentinel-backfill.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sentinel_backfill", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_dead_conditional_removed_from_source() -> None:
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "if False" not in source


def test_is_pull_request_sends_include_flag(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_backoff(*args: str, **kwargs) -> str:
        calls.append(args)
        return "HTTP/2.0 200 OK\n{}"

    monkeypatch.setattr(_MODULE, "gh_with_backoff", fake_backoff)

    assert _MODULE.is_pull_request("o", "r", 12) is True
    assert calls and calls[0][-1] == "-i"
    assert "--silent" not in calls[0]


def test_is_pull_request_retries_rate_limit_then_succeeds(monkeypatch) -> None:
    responses = iter(
        [
            "HTTP/2.0 429 Too Many Requests\nAPI rate limit exceeded",
            "HTTP/2.0 200 OK\n{}",
        ]
    )
    calls: list[tuple[str, ...]] = []

    def fake_gh(*args: str, check: bool = True) -> str:
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(_MODULE, "gh", fake_gh)
    monkeypatch.setattr(_MODULE, "BACKOFF_BASE_SECONDS", 0.0)

    assert _MODULE.is_pull_request("o", "r", 12) is True
    assert len(calls) == 2


def test_gh_with_backoff_retries_with_growing_delays(monkeypatch) -> None:
    outputs = iter(
        [
            '{"message": "API rate limit exceeded"}',
            '{"message": "abuse detection mechanism"}',
            '{"data": {}}',
        ]
    )
    naps: list[float] = []
    monkeypatch.setattr(_MODULE, "gh", lambda *a, **k: next(outputs))

    raw = _MODULE.gh_with_backoff("api", "x", base_delay=1.0, sleep_fn=naps.append)
    assert raw == '{"data": {}}'
    assert naps == [1.0, 2.0]


def test_gh_with_backoff_gives_up_after_max_attempts(monkeypatch) -> None:
    naps: list[float] = []
    monkeypatch.setattr(_MODULE, "gh", lambda *a, **k: "HTTP/2.0 429 Too Many Requests")

    raw = _MODULE.gh_with_backoff("api", "x", max_attempts=3, base_delay=1.0, sleep_fn=naps.append)
    assert "429" in raw
    assert naps == [1.0, 2.0]


def test_close_event_recovers_through_rate_limit(monkeypatch) -> None:
    good = json.dumps(
        {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [{"closer": {"__typename": "PullRequest", "number": 77}}],
                        }
                    }
                }
            }
        }
    )
    responses = iter(['{"message": "API rate limit exceeded for user"}', good])

    def fake_gh(*args: str, check: bool = True) -> str:
        return next(responses)

    monkeypatch.setattr(_MODULE, "gh", fake_gh)
    monkeypatch.setattr(_MODULE, "BACKOFF_BASE_SECONDS", 0.0)

    assert _MODULE.resolve_via_close_event("o", "r", 5) == 77


def test_checkpoint_round_trip_and_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "progress.json"
    assert _MODULE.load_checkpoint(path) == {}
    _MODULE.save_checkpoint(path, {7: 42, 9: 10})
    assert _MODULE.load_checkpoint(path) == {7: 42, 9: 10}
    path.write_text("not json {{{")
    assert _MODULE.load_checkpoint(path) == {}
    path.write_text(json.dumps({"anchors": {"x": "y", "3": 4}}))
    assert _MODULE.load_checkpoint(path) == {3: 4}


def _run_main(monkeypatch, tmp_path: Path, argv: list[str], universe: list[int]) -> dict:
    monkeypatch.setattr(_MODULE, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_MODULE, "ANCHORS_PATH", tmp_path / "sentinel_anchors.json")
    monkeypatch.setattr(_MODULE, "CHECKPOINT_PATH", tmp_path / "sentinel_backfill.progress.json")
    monkeypatch.setattr(_MODULE, "detect_repo", lambda: ("o", "r"))
    monkeypatch.setattr(_MODULE, "load_universe", lambda: ({}, universe))
    monkeypatch.setattr(_MODULE, "resolve_via_close_event", lambda o, r, n: None)
    monkeypatch.setattr(sys, "argv", ["sentinel-backfill.py", *argv])
    naps: list[float] = []
    monkeypatch.setattr(_MODULE.time, "sleep", naps.append)
    monkeypatch.setattr(_MODULE, "BACKOFF_BASE_SECONDS", 0.0)
    return {"naps": naps}


def test_main_paces_between_issues(monkeypatch, tmp_path: Path) -> None:
    ctx = _run_main(monkeypatch, tmp_path, ["--delay", "0.25", "--dry-run"], [3, 2, 1])
    monkeypatch.setattr(_MODULE, "resolve_via_comments", lambda o, r, n, delay=0.0: 99)
    assert _MODULE.main() == 0
    assert ctx["naps"] == [0.25, 0.25]


def test_main_resume_skips_checkpointed_issues(monkeypatch, tmp_path: Path) -> None:
    _run_main(monkeypatch, tmp_path, ["--resume", "--delay", "0"], [7, 8])
    _MODULE.save_checkpoint(_MODULE.CHECKPOINT_PATH, {7: 42})
    seen: list[int] = []

    def fake_comments(owner: str, repo: str, num: int, *, delay: float = 0.0) -> int | None:
        seen.append(num)
        return 100 + num

    monkeypatch.setattr(_MODULE, "resolve_via_comments", fake_comments)
    assert _MODULE.main() == 0
    assert seen == [8]
    payload = json.loads((_MODULE.ANCHORS_PATH).read_text())
    assert payload["anchors"] == {"7": 42, "8": 108}
    assert not _MODULE.CHECKPOINT_PATH.exists()
