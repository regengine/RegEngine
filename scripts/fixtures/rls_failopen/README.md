# RLS fail-open guard fixtures (#2935)

`bad/` holds policy snippets that `scripts/check_rls_fallback.py` MUST reject.
`good/` holds fail-closed policies it MUST accept.

These are inputs to the guard's own test suite
(`tests/scripts/test_check_rls_fallback.py`), not migrations: nothing under
`scripts/` is ever executed by Alembic. Point the guard at them directly with

    python scripts/check_rls_fallback.py scripts/fixtures/rls_failopen/bad

Before #2935 the guard's primary regex could not match the canonical snippet
quoted in its own docstring, it never opened `alembic/sql/`, and it never
inspected a `WITH CHECK` clause. Every file in `bad/` reproduces one of those
holes; a future regex refactor that reopens one turns the suite red.
