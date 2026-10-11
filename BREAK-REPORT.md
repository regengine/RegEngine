# CLI break report

1 break found. 1 fixed and tested. 0 fixed but still failing. 0 blocked.

The RegEngine CLI in `cli/` is a stub with no subcommands. Bad arguments, retired commands, and path-like tokens already exit with code 2. The CLI does not read those paths and does not open a network connection. The real break is an import shadow: `cli/regengine.py` can be loaded as the top-level module `regengine`, hiding the SDK package.

## High: importing regengine can load the CLI file instead of the SDK

What broke: With `cli/` first on `sys.path`, `import regengine` loaded `cli/regengine.py`. That file is the CLI stub. It is not the SDK, so `from regengine import RegEngineClient` failed. `python cli/regengine.py` puts `cli/` first on `sys.path` for that process, which is the same shape. A full `mypy .` run also stopped immediately on a duplicate module named `regengine` (the SDK package and `cli/regengine.py`). That duplicate is gone. Full mypy now stops on a different, pre-existing duplicate (`tests/audit/verify_chain.py` and `frontend/public/sdk/verify_chain.py`), which this change does not touch.

How to reproduce: From the repo root, put `cli/` ahead of the repo root on `sys.path` and import `regengine`. The module file is `cli/regengine.py`, and `RegEngineClient` is missing. Before this change, `import cli` was a namespace package (`cli.__file__` is `None`), which is why mypy treated `cli/regengine.py` as a second top-level `regengine`.

Root cause: `cli/regengine.py` (module body, previously the bare `import click` at the top of the file). The directory was not a regular package, and the file name is `regengine.py`. Python's script launcher inserts that directory at the front of `sys.path`.

Fix: `cli/__init__.py` makes `cli` a regular package so the module name is `cli.regengine`. On import, `cli/regengine.py` removes that directory from `sys.path` before it imports Click. If the file was loaded as the top-level name `regengine`, it imports the real SDK and places that module in `sys.modules`. If no SDK package is on the path, the import raises `ImportError` instead of returning the stub.

Test results: `~/metacode/fleet/heavy .venv/bin/pytest tests/cli/test_regengine_cli.py --tb=line --no-header` after the fix: 24 passed in 1.01s. `.venv/bin/ruff check cli/regengine.py cli/__init__.py tests/cli/test_regengine_cli.py`: all checks passed. Targeted mypy of `cli/regengine.py`, `cli/__init__.py`, and `regengine/__init__.py` exited 0. A full `mypy .` no longer reports the `regengine` duplicate.

Confirmed the new tests fail without the fix: the same pytest command, run before `cli/regengine.py` and `cli/__init__.py` were changed, failed `test_import_regengine_is_the_sdk_when_cli_dir_is_first_on_the_path` and `test_import_regengine_does_not_load_the_cli_file_when_the_sdk_is_absent` with `ImportError: cannot import name 'RegEngineClient' from 'regengine' (.../cli/regengine.py)` and `loaded .../cli/regengine.py`. `test_cli_is_a_regular_package` failed because `cli.__file__` was `None`. After the script-shadow test was pointed at that path shape, it failed the same way (`RegEngineClient` imported from `cli/regengine.py`).

## Checked, not a break

- Unknown commands (`nosuch`, `compile`, `list-verticals`, `validate`, empty string, `..`, a long token, `--version`, `-h`) exit 2.
- A path passed as a command is not read. A sentinel file's text does not appear in the output.
- A null byte in the command raises Click's usage error with a non-zero exit code.
- Running the CLI with a socket `connect` guard exits 2 and does not attempt a connection.
- Four parallel unknown-command processes each exit 2.
- `--help` exits 0. Click still treats `--help` as eager, so `python -m cli.regengine --help nosuch` exits 0. That is Click's help handling, not a failed command path. A real unknown command without `--help` exits 2.
- There is no auth surface on this stub, so there is no auth bypass to close.
- No production URL is contacted. Tests are local subprocesses only.

## Open questions

- Full `mypy .` still stops on the unrelated `verify_chain` duplicate named above. That is outside `cli/`.
- `python cli/regengine.py` remains supported. `python -m cli.regengine` remains the entry point named in the module docstring.
