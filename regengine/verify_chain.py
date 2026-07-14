"""Deprecated module name — use :mod:`regengine.verify_records`.

This module was renamed (WS-11) to end the filename collision with the
Merkle *bundle* verifier published at
https://regengine.co/sdk/verify_chain.py — a different program that only
shared this file's name. All symbols re-export from
``regengine.verify_records``; this shim will be removed before the first
PyPI release.
"""

import warnings

from .verify_records import *  # noqa: F401,F403
from .verify_records import main  # noqa: F401

warnings.warn(
    "regengine.verify_chain is deprecated; import regengine.verify_records "
    "instead (renamed in WS-11 to disambiguate from the Merkle bundle "
    "verifier served at /sdk/verify_chain.py).",
    DeprecationWarning,
    stacklevel=2,
)
