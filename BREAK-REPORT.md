# Break Report: services/shared/fsma and shared auth helpers

## Summary

Adversarial testing (null inputs, mistyped inputs, boundary values, a
threaded rate-limit hammer, malformed credentials) found 5 real breaks.
All 5 are fixed and tested: 26 new regression tests pass, 17 of them fail
on the pre-fix code. Fixed but failing: 0. Blocked: 0. No live services,
no production URLs, and no database were touched; everything ran against
local pytest only. Webhook HMAC secret wiring was left alone per the task
boundary.

## Finding 1 (high): validate_input decorator silently dropped sanitized values

What broke: decorating a function with `@validate_input(name=...)` ran
validation but then called the function with the original arguments, so
any normalized or sanitized value (for example HTML stripped by
`TextContentField`) never reached the function body. A caller relying on
the decorator for sanitization got the raw input back.

How to reproduce: decorate `def greet(name): return name` with
`@validate_input(name=TextContentField(allow_html=False))` and call
`greet("<b>hi</b>")`. Old code returned `'<b>hi</b>'`.

Root cause: `services/shared/input_validation.py:451` (`_validate_args`
mutated `bound.arguments` but both wrappers called `func(*args,
**kwargs)`).

Fix: the wrappers now call the function with the rebuilt
`bound.args`/`bound.kwargs`, for sync and async paths.

Test results: 5 new tests pass (sync sanitization, positional args,
async, rejection still raises, identifier still passes through).
Verified the 3 sanitization tests fail on pre-fix code.

## Finding 2 (high): API key validation crashed on non-string credentials

What broke: `APIKeyStore.validate_key` and
`DatabaseAPIKeyStore.validate_key` (plus `set_api_key_lookup_context`)
called `.startswith("rge_")` without a type check, so a mistyped
credential (integer, list) raised `AttributeError`, which surfaces as a
500 instead of an auth rejection.

How to reproduce: `APIKeyStore().validate_key(12345)` raised
`AttributeError: 'int' object has no attribute 'startswith'`.

Root cause: `services/shared/auth.py:179`,
`services/shared/api_key_store.py:120` (lookup context) and
`services/shared/api_key_store.py:748` (DB store).

Fix: `isinstance(raw_key, str)` guard first, returning `None` (invalid
key) for anything else. The DB lookup-context path returns `None`
without touching the database.

Test results: new tests pass, including a round-trip test proving valid
keys still validate and tampered keys still fail. Verified the mistyped
tests fail on pre-fix code.

## Finding 3 (medium): permission helpers crashed on null or mistyped grants

What broke: `permission_implies(None, "read")` and
`has_permission([None], "read")` raised `AttributeError` from
`str.strip()`. Scopes come from key rows consumed by ingestion and
billing authz paths, so one junk entry turned an authorization check
into a 500.

How to reproduce: `permission_implies(None, "read")` raised
`AttributeError: 'NoneType' object has no attribute 'strip'`.

Root cause: `services/shared/permissions.py:17` (`_normalize` assumed
`str`).

Fix: non-string input normalizes to `""`, so the implication check
returns `False` (fail closed). Wildcard and separator behavior is
unchanged.

Test results: new tests pass (`None`, `123`, junk entries skipped, empty
list denied, wildcards intact). Verified the misuse tests fail on
pre-fix code.

## Finding 4 (medium): FSMA identifier helpers raised raw errors on null input

What broke: `normalize_gtin(None)`, `extract_company_prefix(None)`,
`calculate_gs1_check_digit(None)`, `calculate_gs1_check_digit(123)`,
`detect_identifier_type(None)`, `validate_gln(123)`,
`validate_identifier(None)`, and `verify_gs1_check_digit(123)` raised
raw `TypeError` or `AttributeError` instead of failing closed. The
shared error handler maps `ValueError` to a client-safe 400, so raw
errors were the difference between a clean rejection and a 500.

How to reproduce: each call above raised on pre-fix code (observed in
the probe run before any edit).

Root cause: `services/shared/fsma_validation.py` helpers called
`re.sub`, `.isdigit()`, or `re.fullmatch` on unvalidated input.

Fix: pure converters (`normalize_gtin`, `extract_company_prefix`,
`calculate_gs1_check_digit`) raise `ValueError` with a clear message
for non-string input; boolean checks (`verify_gs1_check_digit`) return
`False`; detectors and validators (`_detect_identifier_type`,
`validate_gln/gtin/sscc`, `validate_identifier`) return UNKNOWN or an
invalid result. Valid-input behavior is unchanged.

Test results: new tests pass, including a TLC strict-mode boundary
(14 digits alone invalid, 14 digits plus suffix valid). Verified the
misuse tests fail on pre-fix code.

## Finding 5 (low): jurisdiction check crashed on mistyped input

What broke: `verify_jurisdiction_access` called `.split()` on the
requested jurisdiction and `in`/`startswith` on entitlement entries, so
a non-string request or a junk entitlement entry raised instead of
denying with 403.

How to reproduce: `verify_jurisdiction_access(key, 123)` raised
`AttributeError` on pre-fix code.

Root cause: `services/shared/auth.py:445` (now shifted by the guard
edit).

Fix: coerce the request with `str(...)` and skip non-string
entitlement entries, so malformed input always ends in 403. Federal
root and entitlement matching are unchanged.

Test results: new tests pass (`None`, `123`, `""` all 403; `US` still
allowed; `US-CA` still entitled; `US-TX` still denied). Verified the
mistyped tests fail on pre-fix code.

## Concurrency and boundary probes with no break

Threaded hammer of `APIKeyStore.check_rate_limit` (8 threads x 20
calls, limit 10) allowed exactly 10, so the lock discipline holds.
Rate-limit exact boundary (5 of 6 allowed at limit 5) is correct.
`TimeArrowRule` failing open on unparseable dates was investigated and
deliberately left alone: both call sites (`chain_integrity.py` and
`tracer.py`) already compensate for that behavior, and changing it
would invert their skip logic. The 13-digit GTIN versus GLN
auto-detect ambiguity was left as a documented open question below.

## Open questions

1. Should `validate_identifier` prefer GTIN over GLN for 13-digit
   numeric input, or keep reporting GLN and require callers to pass
   `expected_type`? Both shapes share the check-digit algorithm, so
   only the label differs.
2. Should `TimeArrowRule` gain an opt-in strict mode that flags
   unparseable dates, so future callers can choose fail-closed without
   changing the two existing call sites?
3. `APIKeyStore` keeps an unbounded in-memory rate-limit map; fine for
   its documented non-production role, but worth noting if its use
   ever widens.
