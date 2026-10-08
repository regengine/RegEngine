# BREAK-REPORT: launch_orchestrator adversarial testing

## Summary

Probed `launch_orchestrator/` with 14 adversarial probes covering bad spec
YAML, missing templates, and dry-run safety. Found 10 real breaks, fixed all
10 in `launch_orchestrator/orchestrator.py`, and added 26 regression tests in
`tests/scripts/test_launch_orchestrator_breakit.py`.

Counts: 10 breaks found, 10 fixed and tested, 0 fixed but failing, 0 blocked.
All testing was local only (scratch directories, bare `echo` commands, throwaway
spec files). No production URL was called, no real deployment ran, no
background processes were left running.

Verification: 26 new tests pass on the fixed code; 23 of them fail on the
pre-fix code (the other 3 are pins that pass on both, noted below). The two
pre-existing orchestrator suites (22 tests) still pass. `ruff check` and
`ruff format --check` are clean on both touched files.

## Findings (sorted by severity)

### 1. High: flipping `dry_run` after construction bypassed the production guard

What broke: the `REGENGINE_ENV=production` check ran only inside `__init__`.
Setting `orch.dry_run = False` on a dry-run instance (or calling a phase
method directly) executed real deployment commands with no guard at all.
Reproduce: build a dry-run orchestrator on a scratch spec, set
`orch.dry_run = False` with `REGENGINE_ENV` unset, call
`_execute_deployment(..., 'echo "LIVE"', ...)`. Pre-fix, the command ran.

Root cause: `launch_orchestrator/orchestrator.py:159` (old numbering), guard
only in `__init__`, while `dry_run` is a mutable attribute.

Fix: new `_assert_live()` method re-checks `REGENGINE_ENV=production` on every
live path: `_execute_deployment`, and the file-write branches of
`_generate_persona_collateral` and `_provision_sandbox`. Post-fix the probe
raises `RuntimeError`, and the sandbox probe writes nothing to disk.

Test results: `test_flipped_dry_run_still_requires_production_guard` and
`test_live_write_paths_require_production_guard` pass on fixed code, fail on
pre-fix code.

### 2. High: missing campaign templates reported success

What broke: `_initialize_outbound_sequence` never checked that a step's
`template_ref` file exists, so a campaign pointing at deleted or mistyped
templates recorded `success` and the break surfaced only at send time.
Reproduce: spec with one sequence whose step references
`templates/email/NOPE_missing.md`, run sales-only dry run. Pre-fix, the event
was `success`.

Root cause: `launch_orchestrator/orchestrator.py`, `_initialize_outbound_sequence`
had no existence check.

Fix: each step's `template_ref` is resolved against `base_dir` and must be a
file; otherwise the sequence records `failure` naming the missing templates
and the run continues with the remaining sequences.

Test results: `test_missing_sequence_template_records_failure` (fails pre-fix)
and `test_present_sequence_template_records_success` (passes both, locks in
the happy path).

### 3. High: minimal spec crashed with IsADirectoryError

What broke: with no `design_partner_program` or `investor_readiness` section,
`base_dir / ""` resolves to the base directory itself, `.exists()` is True for
a directory, and `add_artifact` crashed opening it. A minimal but valid spec
failed a dry run with `[Errno 21] Is a directory` and aborted all later phases.
Reproduce: spec containing only `orchestrator` and `environment`, full dry run.

Root cause: `launch_orchestrator/orchestrator.py`, `_provision_design_partners`
and `_prepare_investor_materials` used `.exists()` on a possibly empty ref.

Fix: empty ref records an honest `skipped` event; a configured-but-absent file
records `failure` naming the ref; only a real file records `success`
(`is_file()` instead of `exists()`).

Test results: `test_minimal_spec_dry_run_skips_optional_templates`,
`test_missing_legal_template_records_failure`,
`test_missing_investor_memo_records_failure`. All three fail pre-fix.

### 4. High: bad spec YAML crashed mid-run with bare KeyError, TypeError, AttributeError

What broke: six malformed-spec shapes aborted the whole run with confusing
errors and skipped every remaining phase: step missing `channel` (`KeyError:
'channel'`), persona missing `id` (`KeyError: 'id'`), status component missing
`name` (`KeyError: 'name'`), `max_partners: "five"` (`TypeError` in `range`),
`required_env_vars: "FOO"` (validated per-character names `F`, `O`, `O`),
empty spec file (`TypeError: argument of type 'NoneType'`), string
`environment` (`AttributeError`), null `required_env_vars` (`TypeError`).

Root cause: `launch_orchestrator/orchestrator.py`, `_load_config` checked only
top-level key presence and validated nothing else.

Fix: new `_validate_config_schema()` runs at load and raises `ValueError`
with a dotted field path (for example
`sales.outbound_campaigns.sequences[0].steps[0].channel`). Null
`required_env_vars` normalizes to `[]`. Bad specs now fail fast at
construction instead of aborting a run halfway.

Test results: 12 tests (`test_empty_spec_file_raises_value_error` through
`test_string_workspaces_raises_at_load` plus the null normalization test).
All fail pre-fix except none; the null case returned `success False` pre-fix
and `True` post-fix.

### 5. Medium: missing binary aborted the run instead of recording one failure

What broke: `_execute_deployment` caught only `CalledProcessError`, so a
nonexistent deploy binary escaped as `FileNotFoundError`, aborted every
remaining phase, and left only a generic `orchestration_execution` error.
Reproduce: non-dry-run (with `REGENGINE_ENV=production`, scratch dir) with
`deploy_command: "definitely-not-a-real-binary-xyz deploy"`.

Root cause: `launch_orchestrator/orchestrator.py`, `_execute_deployment`
except clause too narrow.

Fix: catch `OSError` (covers missing binary, permission errors) and record a
per-action `failure` event so the run continues. Empty or blank commands are
refused with a `failure` event instead of crashing `shlex.split` with
`IndexError` (separate probe, same fix site).

Test results: `test_bogus_binary_records_failure_and_run_continues` and
`test_empty_deploy_command_records_failure`. Both fail pre-fix.

### 6. Medium: hung deploy command blocked the run forever

What broke: `subprocess.run` had no timeout, so a wedged installer or an
interactive prompt on a non-tty hung the orchestrator indefinitely. No crash,
just a silent stall; confirmed by reading the call (no timeout argument) and
by the absence of any `TimeoutExpired` handling.

Root cause: `launch_orchestrator/orchestrator.py`, `_execute_deployment`
called `subprocess.run` unbounded.

Fix: `timeout=_DEPLOY_TIMEOUT_SECONDS` (600) on every deploy subprocess;
`TimeoutExpired` records a per-action `failure` and the run continues.

Test results: `test_deploy_passes_a_timeout` and
`test_deploy_timeout_records_failure`. Both fail pre-fix. The 600 second value
is a judgment call; see open questions.

### 7. Medium: result file write was not atomic

What broke: `_finalize_result` wrote with `open("w")`, so a crash mid-write
left a truncated `orchestration_result.json`. While fixing this, the new
concurrency test caught a second live race: same-pid threads shared one tmp
name, so parallel dry runs collided with `FileNotFoundError`. Both are fixed
by a pid plus thread-id tmp name with `os.replace`.

Root cause: `launch_orchestrator/orchestrator.py`, `_finalize_result` direct
write; first fix attempt used a pid-only tmp name.

Fix: write `.orchestration_result.json.<pid>.<thread>.tmp`, then `os.replace`.

Test results: `test_failed_result_write_keeps_previous_file` (fails pre-fix:
sentinel destroyed) and `test_concurrent_dry_runs_leave_valid_result_json`
(failed mid-fix with the tmp collision, passes now; passes on pre-fix code
too, kept as a pin).

### 8. Low (no break found, pinned): shell metacharacters stay inert

Probed `echo hi; touch <marker>` through the live path. `shlex.split` without
`shell=True` passes the metacharacters literally; the marker was never
created. `test_shell_metacharacters_are_not_interpreted` locks this in and
passes on both versions.

## Open questions

1. The 600 second deploy timeout is my choice, not a repo standard. If real
   Terraform applies run longer, the first slow production deploy will tell us.
   Christopher should confirm or adjust `_DEPLOY_TIMEOUT_SECONDS`.
2. Importing `orchestrator.py` creates `orchestrator.log` in the current
   working directory via the module-level `FileHandler`. Test runs therefore
   leave a log file at the repo root (gitignored, harmless). Not changed;
   lazy logging setup would be a bigger edit than this task warrants.
3. `_finalize_result` still writes `orchestration_result.json` next to the spec
   even in dry-run mode. That dirties the tree on a simulation run, but the
   README documents it as output, so it was left as is.
4. With the default shipped spec, `investor_readiness.memo_template_ref`
   points at `investors/investor_memo.md`, which does not exist in the repo, so
   a full dry run now honestly reports `success False` for that phase. That is
   the intended behavior change (no more false success), but it means the
   default spec does not fully pass until the memo template ships.
