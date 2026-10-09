"""No invalid escape sequences in the RLS guard self-tests.

Regression test for the audit finding: a docstring in
``tests/scripts/test_check_rls_fallback.py`` contained ``\\s``, which raises
SyntaxWarning today and becomes SyntaxError in a future Python version.
Compiling the file with SyntaxWarning promoted to an error fails on the
old code and passes once the docstring is a raw string.
"""

from __future__ import annotations

import py_compile
import warnings
from pathlib import Path

_TARGET = Path(__file__).with_name("test_check_rls_fallback.py")


def test_no_invalid_escape_sequences():
    # Python emits DeprecationWarning before 3.12 and SyntaxWarning from
    # 3.12 on, so promote both to errors to catch the bad escape anywhere.
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        warnings.simplefilter("error", DeprecationWarning)
        py_compile.compile(str(_TARGET), doraise=True)
