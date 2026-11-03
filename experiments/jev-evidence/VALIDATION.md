# Validation record

- Live final comparison: 100 HTTP 200 responses; no retries or harness errors. Candidate: 34/34 regression and 16/16 fresh cases. Reference: 33/34 regression and 16/16 fresh cases.
- `npm test`: 80 passed, 0 failed in the standalone delivery and the isolated repository checkout.
- `node analyze-offline.mjs`: all 100 saved classifications, frozen labels/hashes, raw usage, and cost totals reconcile.
- Existing repository TypeScript compiler with this package's `tsconfig.json`: passed.
- Saved TypeSafe OpenAPI snapshot: 100 requests and 100 responses valid.
- `python3 scripts/check_workflow_inventory.py`: 34 workflows, 4 required contexts, passed.
- `pre-commit run`: all applicable hooks passed, including detect-secrets.
- `gitleaks protect --staged --redact --no-banner`: no leaks found.
- TruffleHog scan with the explicit branch and full base commit, plus filesystem scan of the new package: zero verified or unknown findings. An earlier symbolic-HEAD scan wandered into unrelated historical commits; no clean-history claim is made for the whole repository.
- 570 detect-secrets checksum findings were individually matched to SHA-256 hashes of actual preserved output files before exact false-positive baseline entries were added. Existing scanner plugins, filters, exclusions, and prior baseline entries were unchanged. One clearly synthetic mocked transport marker is annotated at its test-only declaration.
- Independent gate review reconciled the live evidence, budget, preservation checks, runner safeguards, and offline CI integration. Supplementary Muse review of selected runner/replay/test code returned PASS.
- All 521 artifacts existing before this implementation remained byte-identical. The rejected first revision remains available with its failed B08 test and original responses.

This record concerns local checks before the commit. Remote CI and merge status are recorded by the pull request. CI replays saved synthetic responses and mocks transport; it makes no Jev API calls.
