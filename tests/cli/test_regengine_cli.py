"""Adversarial checks for the RegEngine CLI stub.

The CLI has no subcommands. These tests pin three things:

* bad arguments, retired commands, and path-like tokens fail with a non-zero
  exit code and do not read the path or open a socket
* ``import regengine`` still loads the SDK when ``cli/`` is first on
  ``sys.path`` (that is what ``python cli/regengine.py`` does)
* ``cli`` is a real package, so this file is ``cli.regengine`` and not a
  second top-level module named ``regengine``
"""

from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from click.exceptions import ClickException

REPO = Path(__file__).resolve().parents[2]
CLI_FILE = REPO / "cli" / "regengine.py"
SDK_INIT = REPO / "regengine" / "__init__.py"

# Child processes rebuild sys.path themselves. Keep the snippets in the test
# file so the failure is visible without a second module.
_SHADOW_WITH_SDK = r"""
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
cli_dir = str(repo / "cli")
root = str(repo)
rest = [entry for entry in sys.path if entry not in (cli_dir, root, "")]
sys.path[:] = [cli_dir, root, *rest]
sys.modules.pop("regengine", None)
import regengine
from regengine import RegEngineClient

location = Path(regengine.__file__).resolve()
if location == (repo / "cli" / "regengine.py").resolve():
    raise SystemExit("shadowed")
if not RegEngineClient.__module__.startswith("regengine"):
    raise SystemExit("wrong client")
print(location)
"""

_SHADOW_WITHOUT_SDK = r"""
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
cli_dir = repo / "cli"
kept = []
for entry in list(sys.path):
    if not entry:
        continue
    try:
        resolved = Path(entry).resolve()
    except OSError:
        continue
    if resolved == repo or repo in resolved.parents:
        continue
    if (resolved / "regengine" / "__init__.py").is_file():
        continue
    kept.append(entry)
sys.path[:] = [str(cli_dir), *kept]
sys.modules.pop("regengine", None)
try:
    import regengine
except ImportError:
    raise SystemExit(0)
origin = getattr(regengine, "__file__", "")
raise SystemExit("loaded " + str(origin))
"""

_SCRIPT_THEN_IMPORT = r"""
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
cli_file = repo / "cli" / "regengine.py"
cli_dir = str(cli_file.parent)
root = str(repo)
rest = [entry for entry in sys.path if entry not in (cli_dir, root, "")]
# Same path shape as `python cli/regengine.py` when the repo is also on
# PYTHONPATH: this directory is first, so it would win an import.
sys.path[:] = [cli_dir, root, *rest]
sys.modules.pop("regengine", None)
namespace = {
    "__name__": "cli.regengine",
    "__file__": str(cli_file),
    "__package__": "cli",
}
exec(compile(cli_file.read_text(encoding="utf-8"), str(cli_file), "exec"), namespace)
sys.modules.pop("regengine", None)
import regengine
from regengine import RegEngineClient

location = Path(regengine.__file__).resolve()
if location == cli_file.resolve():
    raise SystemExit("shadowed")
if not RegEngineClient.__module__.startswith("regengine"):
    raise SystemExit("wrong client")
print(location)
"""

_NO_NETWORK = r"""
import socket
import sys
import runpy

class Guard(socket.socket):
    def connect(self, address):
        raise RuntimeError("network connect")
    def connect_ex(self, address):
        raise RuntimeError("network connect_ex")

socket.socket = Guard
sys.argv = ["cli.regengine", "nosuch"]
runpy.run_module("cli.regengine", run_name="__main__")
"""


def _child(code: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cli.regengine", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_import_regengine_is_the_sdk_when_cli_dir_is_first_on_the_path() -> None:
    result = _child(_SHADOW_WITH_SDK, str(REPO))
    assert result.returncode == 0, result.stderr
    assert "shadowed" not in result.stderr
    assert str(SDK_INIT) in result.stdout


def test_import_regengine_does_not_load_the_cli_file_when_the_sdk_is_absent() -> None:
    result = _child(_SHADOW_WITHOUT_SDK, str(REPO))
    combined = result.stdout + result.stderr
    assert result.returncode == 0, combined
    assert "loaded " not in combined
    assert "cli/regengine.py" not in combined


def test_running_the_script_does_not_leave_the_cli_dir_shadowing_the_sdk() -> None:
    result = _child(_SCRIPT_THEN_IMPORT, str(REPO))
    assert result.returncode == 0, result.stderr
    assert str(SDK_INIT) in result.stdout


def test_cli_is_a_regular_package() -> None:
    import cli

    package_file = getattr(cli, "__file__", None)
    assert package_file is not None
    assert Path(package_file).name == "__init__.py"

    import cli.regengine as cli_mod

    assert cli_mod.__name__ == "cli.regengine"
    assert callable(cli_mod.cli)


@pytest.mark.parametrize(
    "args",
    [
        ["nosuch"],
        ["compile"],
        ["list-verticals"],
        ["validate"],
        [""],
        [".."],
        ["../../../../etc/passwd"],
        ["--data-path"],
        ["--file"],
        ["--token=secret"],
        ["-h"],
        ["--version"],
        ["a" * 8000],
    ],
)
def test_bad_args_exit_nonzero(args: list[str]) -> None:
    result = _cli(*args)
    assert result.returncode == 2
    assert "TOP-SECRET-SENTINEL" not in result.stdout + result.stderr


def test_help_exits_zero_and_names_no_commands() -> None:
    result = _cli("--help")
    assert result.returncode == 0
    assert "No commands are currently registered" in result.stdout


def test_bare_invocation_exits_nonzero() -> None:
    result = _cli()
    assert result.returncode == 2


def test_script_path_unknown_command_exits_nonzero() -> None:
    result = subprocess.run(
        [sys.executable, str(CLI_FILE), "nosuch"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 2
    assert "No such command" in result.stderr


def test_path_like_argument_is_not_read(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-SENTINEL-VALUE", encoding="utf-8")
    result = _cli(str(secret), "--data-path", str(tmp_path / "outside"))
    combined = result.stdout + result.stderr
    assert result.returncode == 2
    assert "TOP-SECRET-SENTINEL-VALUE" not in combined
    assert secret.read_text(encoding="utf-8") == "TOP-SECRET-SENTINEL-VALUE"


def test_null_byte_command_fails_closed() -> None:
    import cli.regengine as cli_mod

    with pytest.raises(ClickException) as excinfo:
        cli_mod.cli.main(args=["\x00"], prog_name="regengine", standalone_mode=False)
    assert excinfo.value.exit_code != 0


def test_cli_does_not_open_a_network_connection() -> None:
    result = _child(_NO_NETWORK)
    combined = result.stdout + result.stderr
    assert result.returncode == 2, combined
    assert "network connect" not in combined


def test_parallel_unknown_commands_all_fail() -> None:
    def run_one(index: int) -> int:
        completed = _cli(f"bad-command-{index}")
        return completed.returncode

    with ThreadPoolExecutor(max_workers=4) as pool:
        codes = list(pool.map(run_one, range(4)))
    assert codes == [2, 2, 2, 2]
