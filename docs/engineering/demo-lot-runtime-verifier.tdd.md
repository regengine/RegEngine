# DEMO-LOT-0412 runtime verifier TDD evidence

## Source and user journey

No plan file was supplied. The acceptance criteria came directly from the delegated task.

As a release verifier, I want a GET-only production probe that validates the built-in DEMO-LOT-0412 scenario while keeping the API key and full CSV out of its output, so that runtime evidence can be captured safely.

## RED and GREEN checkpoints

- RED commit `fe15abf5`: `python -m pytest tests/scripts/test_verify_demo_lot_runtime.py` failed during collection because `scripts/verify_demo_lot_runtime.py` did not exist (`FileNotFoundError`; 1 error).
- GREEN commit `2a965954`: the same target passed after the minimal verifier was added (`22 passed in 0.18s`).

## Test specification

| Guarantee | Test or command | Type | Result |
|---|---|---|---|
| The request method is GET and the credential comes from `REGENGINE_API_KEY`. | `test_success_uses_get_and_emits_only_sanitized_evidence` | Unit | PASS |
| Output excludes the API key, full CSV, and unrelated scenario data. | `test_success_uses_get_and_emits_only_sanitized_evidence`; `test_main_never_prints_api_key_or_full_csv` | Unit | PASS |
| Missing credentials and non-HTTPS, unapproved, or altered endpoints fail before network access. | `test_missing_environment_key_fails_before_network`; `test_unapproved_endpoint_fails_before_network` | Unit | PASS |
| Non-200 responses, malformed JSON, and wrong top-level response shapes fail closed without response-body disclosure. | `test_non_200_response_fails_without_body_disclosure`; `test_malformed_json_fails_without_body_disclosure`; `test_non_array_payload_fails` | Unit | PASS |
| Missing, duplicate, or field-mismatched DEMO-LOT-0412 scenarios fail closed. | `test_missing_scenario_fails`; `test_duplicate_scenario_fails`; `test_mismatched_scenario_fields_fail` | Unit | PASS |

## Coverage and known gap

`python -m coverage run --include='*/scripts/verify_demo_lot_runtime.py' -m pytest tests/scripts/test_verify_demo_lot_runtime.py` followed by the matching coverage report produced `85%` statement coverage (`89` statements, `13` missed).

No live authenticated request was executed, as required. Network behavior is verified with injected responses; production runtime proof remains dependent on an operator-provided `REGENGINE_API_KEY` with `inflow.read` permission.
