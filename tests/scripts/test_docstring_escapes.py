"""No invalid escape sequences in the RLS guard self-tests.

Regression test for the audit finding: a docstring in
``tests/scripts/test_check_rls_fallback.py`` contained ``\\s``, which raises
SyntaxWarning today and becomes SyntaxError in a future Python version.
Compiling the file with SyntaxWarning promoted to an error fails on the
old code and passes once the docstring is a raw string.
"""

from __future__ import annotations

import warnings
from pathlib import Path

_TARGET = Path(__file__).with_name("test_check_rls_fallback.py")


def test_no_invalid_escape_sequences():
    # Python emits DeprecationWarning before 3.12 and SyntaxWarning from
    # 3.12 on, so promote both to errors to catch the bad escape anywhere.
    # compile() on the file text raises without writing bytecode, so this
    # stays green in read only checkouts.
    source = _TARGET.read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        warnings.simplefilter("error", DeprecationWarning)
        compile(source, str(_TARGET), "exec")
