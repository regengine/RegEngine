"""``scripts/jev_lab`` command line: exit codes, nothing sent without a key, the key never printed.

Contract pinned here (offline; live mode runs against the fake through an
``httpx2.MockTransport``, so nothing reaches the network):

* Without ``TYPESAFE_API_KEY`` and without ``--fake``, every Jev command exits
  2 and sends nothing.
* ``loop``, ``score`` and ``confirm`` run on the fake; ``export`` prints the
  diff from production and the promotion checklist with every pin to update.
* The key never appears in output, the ledger or the cache.
* ``python scripts/jev_lab --help`` runs as a script without putting
  ``scripts/`` on ``sys.path``.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import httpx2
import pytest
import structlog

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "scripts" / "jev_lab"
FAKE_KEY = "ts-lab-cli-test-key-41c7"  # pragma: allowlist secret


def _load_lab():
    if "jev_lab" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "jev_lab", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["jev_lab"] = module
        spec.loader.exec_module(module)
    return sys.modules["jev_lab"]


_load_lab()
from jev_lab import cli, fake_jev, ledger  # noqa: E402


@pytest.fixture
def home(tmp_path):
    lab = ledger.Ledger(tmp_path / "lab")
    lab.ensure()
    lab.split_path.write_text(json.dumps({"salt": "test-salt-0", "created": "2026-01-01T00:00:00Z", "looks": {}}))
    return lab


def _counting(seen: list) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers.get("authorization", ""))
        return fake_jev.handler(request)

    return httpx2.MockTransport(handler)


def _run(capsys, argv, **kwargs):
    with structlog.testing.capture_logs():
        code = cli.main(argv, **kwargs)
    out, err = capsys.readouterr()
    return code, out, err


@pytest.mark.parametrize("command", ["score", "loop", "serve"])
def test_without_a_key_nothing_is_sent(capsys, home, command):
    seen: list = []

    code, out, err = _run(capsys, [command, "--home", str(home.home)], env={}, transport=_counting(seen))

    assert code == 2
    assert "TYPESAFE_API_KEY is not set" in err and "--fake" in err
    assert seen == [] and out == ""


def test_kill_switch_also_sends_nothing(capsys, home):
    seen: list = []
    env = {"TYPESAFE_API_KEY": FAKE_KEY, "REGENGINE_JEV_ENABLED": "false"}

    code, _, err = _run(capsys, ["score", "--home", str(home.home)], env=env, transport=_counting(seen))

    assert code == 2 and "REGENGINE_JEV_ENABLED switches Jev off" in err and seen == []


def test_fake_loop_and_score_run_offline(capsys, home):
    code, out, _ = _run(capsys, ["loop", "--fake", "--generations", "2", "--json", "--home", str(home.home)])

    summary = json.loads(out)
    assert code == 0 and summary["generations"] >= 1
    assert summary["jev"]["mode"] == "fake" and summary["claude_cost_usd"] == 0.0

    code, out, _ = _run(capsys, ["score", "--fake", "--json", "--home", str(home.home)])
    assert code == 0 and set(json.loads(out)["metrics"]) == {"header_mapping", "file_cte"}

    code, out, _ = _run(capsys, ["ledger", "--home", str(home.home)])
    assert code == 0 and "g1" in out and "Incumbent header_mapping" in out


def test_live_mode_never_prints_or_stores_the_key(capsys, home):
    seen: list = []
    env = {"TYPESAFE_API_KEY": FAKE_KEY, "REGENGINE_JEV_MAX_RETRIES": "0"}

    code, out, err = _run(capsys, ["score", "--json", "--home", str(home.home)], env=env, transport=_counting(seen))

    assert code == 0 and seen and all(FAKE_KEY in header for header in seen)
    stored = "".join(path.read_text() for path in home.home.rglob("*") if path.is_file())
    assert FAKE_KEY not in out + err + stored
    assert (home.home / "jev-cache.jsonl").exists()


def test_prompt_key_is_read_hidden_and_never_echoed(capsys, home):
    seen: list = []

    code, out, err = _run(
        capsys,
        ["score", "--prompt-key", "--home", str(home.home)],
        env={},
        transport=_counting(seen),
        read_key=lambda prompt: FAKE_KEY,
    )

    assert code == 0 and seen
    assert FAKE_KEY not in out + err


def test_export_prints_the_diff_and_every_pin_to_update(capsys, home):
    _run(capsys, ["loop", "--fake", "--generations", "2", "--json", "--home", str(home.home)])
    accepted = [row for row in home.generations() if row["outcome"] == "accepted"]
    assert accepted, "the pinned split accepts generation 1 on the fake"
    digest = next(iter(accepted[0]["candidates"].values()))

    code, out, _ = _run(capsys, ["export", digest, "--home", str(home.home)])

    assert code == 0
    assert "differs from production" in out and "\n- production: " in out and "\n+ candidate:  " in out
    assert "grep -rn 'csv-" in out and "scripts/jev_lab confirm " + digest in out
    assert _run(capsys, ["export", "f" * 64, "--home", str(home.home)])[0] == 1


def test_confirm_reports_insufficient_fresh_data(capsys, home):
    code, out, _ = _run(capsys, ["export", "incumbent", "--home", str(home.home)])
    assert code == 0 and "differs from production csv-header-mapping.v3 in: nothing" in out
    digest = home.save_set(next(iter(home.incumbents().values())))

    code, out, _ = _run(capsys, ["confirm", digest, "--fake", "--home", str(home.home)])

    assert code == 0 and "Insufficient fresh data" in out
    assert _run(capsys, ["confirm", "e" * 64, "--fake", "--home", str(home.home)])[0] == 1


def test_reset_and_rotate(capsys, home):
    salt = home.epoch()["salt"]

    assert _run(capsys, ["reset", "--home", str(home.home)])[0] == 0
    assert home.epoch()["salt"] == salt
    assert _run(capsys, ["reset", "--rotate-split", "--home", str(home.home)])[0] == 0
    assert home.epoch()["salt"] != salt


@pytest.mark.parametrize(
    "argv,message",
    [
        (["loop", "--fake", "--generations", "0"], "--generations must be 1 to 25"),
        (["score", "--fake", "--max-jev-requests", "0"], "--max-jev-requests must be at least 1"),
        (["teleport"], "invalid choice"),
    ],
)
def test_bad_usage_exits_1(capsys, home, argv, message):
    code, _, err = _run(capsys, [*argv, "--home", str(home.home)] if argv[0] != "teleport" else argv)

    assert code == 1 and message in err


def test_runs_as_a_script_without_putting_scripts_on_sys_path(tmp_path):
    probe = (
        "import runpy, sys; sys.argv = ['jev_lab', '--help']\n"
        "try:\n"
        f"    runpy.run_path({str(PACKAGE)!r}, run_name='__main__')\n"
        "except SystemExit as exit:\n"
        f"    assert {str(ROOT / 'scripts')!r} not in sys.path, 'scripts/ on sys.path'\n"
        "    raise\n"
    )
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=120, cwd=tmp_path)

    assert result.returncode == 0, result.stderr[-2000:]
    assert "serve" in result.stdout and "confirm" in result.stdout
