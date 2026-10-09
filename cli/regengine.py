#!/usr/bin/env python3
"""
RegEngine CLI
=============
Command-line interface for RegEngine operations.

NOTE: The historical commands (``compile vertical``, ``list-verticals``,
``validate vertical``) were removed alongside ``kernel/control/`` (codegen
+ RCE surface) per the ``epic-g-retire-kernel`` epic. They had no
consumers and were the only known importers of ``kernel.control``. See
``project_kernel_audit_2026_04_17`` and PR #2205 for the broader kernel
retirement plan; this file is intentionally left as a stub so the
entry point keeps working if anything still invokes ``python -m
cli.regengine``.
"""

import importlib
import sys
import threading
from pathlib import Path

# Set while this file is retrying `import regengine` so a second load of the
# same file fails instead of looping.
_SHADOW_RETRY = "_regengine_cli_shadow_retry"
_SHADOW_LOCK = threading.RLock()


def _directory_of_this_file() -> Path:
    return Path(__file__).resolve().parent


def _entry_is_this_directory(entry: str, directory: Path) -> bool:
    candidate = Path.cwd() if entry == "" else Path(entry)
    try:
        return candidate.resolve() == directory
    except OSError:
        return False


def _drop_this_directory_from_sys_path() -> None:
    """Remove this file's directory from sys.path.

    `python cli/regengine.py` puts cli/ first on sys.path. This file is named
    regengine.py, so `import regengine` would load the CLI instead of the SDK
    package that lives at the repo root.
    """
    directory = _directory_of_this_file()
    updated = [entry for entry in sys.path if not _entry_is_this_directory(entry, directory)]
    if updated == sys.path:
        return
    sys.path[:] = updated
    importlib.invalidate_caches()


def _stop_this_file_shadowing_the_sdk() -> None:
    """Keep `import regengine` pointed at the SDK package."""
    with _SHADOW_LOCK:
        _drop_this_directory_from_sys_path()
        if __name__ != "regengine":
            return
        if getattr(sys, _SHADOW_RETRY, False):
            raise ImportError(
                "cli/regengine.py shadowed the regengine package, and no separate "
                "regengine package is available on the import path."
            )
        setattr(sys, _SHADOW_RETRY, True)
        try:
            sys.modules.pop("regengine", None)
            real = importlib.import_module("regengine")
        finally:
            setattr(sys, _SHADOW_RETRY, False)
        real_file = getattr(real, "__file__", None)
        this_file = Path(__file__).resolve()
        if real_file is None or Path(real_file).resolve() == this_file:
            raise ImportError(
                "cli/regengine.py shadowed the regengine package, and no separate "
                "regengine package is available on the import path."
            )
        sys.modules["regengine"] = real


_stop_this_file_shadowing_the_sdk()

import click


@click.group()
def cli():
    """RegEngine - Regulatory Compliance Engine CLI

    No commands are currently registered. The previous vertical-compiler
    commands were retired with ``kernel/control/``.
    """
    pass


if __name__ == "__main__":
    cli()
