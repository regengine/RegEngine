# FIX-REPORT: PR #3247 latent TLS and service-mesh gaps

Merge commit 7c3207e30ccefc42c39a11ca0b975e1bb9fd1757, fixed on top of origin/main e854dadc.
Scope: confirmed CONCERN and BLOCKER findings from all six re-rv-3247 angles plus the
angle and area leads that mention #3247. No critical findings were filed for #3247.
Out of scope items (other tasks own them, untouched here): the suspended-tenant deny on
live auth, the tenant-scope gate failure, and the 7 xfail cross-tenant leaks. None of
those touch the #3247 files.

## Findings

| # | Source report | Severity | Finding | Status | Reason |
|---|---|---|---|---|---|
| 1 | re-rv-3247-correct, area-infra lead | High | OTel default pair contradicts itself: endpoint defaults to plaintext `jaeger:4317` while `tls.insecure` defaults to false, so a default run dials TLS at a plaintext address and export fails | FIXED AND TESTED | Default flipped to `insecure: true` to match the plaintext default endpoint; comments document that production must set both `JAEGER_OTLP_ENDPOINT` and `JAEGER_OTLP_INSECURE=false` together; added commented `ca_file` knob. Test replaced with a default-consistency test plus configurability pins |
| 2 | re-rv-3247-correct, area-infra lead | Medium | Ingress sets `force-ssl-redirect: true` with a `tls` block but no `ClusterIssuer` exists in the repo, so applying it redirects to HTTPS that never comes up | FIXED AND TESTED | Documented the out-of-repo dependency and the apply order (issuer must exist, wait for `regengine-tls` before relying on the redirect) in the manifest; pinned `secretName == regengine-tls` and the `letsencrypt-prod` issuer annotation in tests |
| 3 | re-rv-3247-correct, area-infra lead | Medium | Nginx upstream `admin-service:8400` hits a closed Service port (the Service publishes 80, targetPort 8400); same defect on all five upstreams, worst on compliance (`:8500`, which matches neither Service nor container port) | FIXED AND TESTED | All five upstreams now dial Service port 80, matching the Ingress convention; added a test that every upstream host:port matches a k8s Service name:port, plus a stale-container-port ban |
| 4 | re-rv-3247-security, area-infra lead | Medium | Gateway presents itself as a TLS fix while the only live server listens on plaintext port 80, and the TLS tests assert on commented directives | FIXED AND TESTED | TLS tests relabeled as template checks; added a live-state pin asserting on uncommented directives only (fails if someone half-enables TLS); added the missing commented 301 line the port 80 note refers to |
| 5 | re-rv-3247-tests, area-infra lead | High | `infra/gateway/tests` is in no pytest invocation, so the nginx tests never run | FIXED AND TESTED | Added `infra/gateway/tests` to `pyproject.toml` testpaths and to the test-suite-check representation guard; verified the suite collects and passes |
| 6 | re-rv-3247-tests, area-infra lead | High | `tests/infra` only runs when backend paths change, so an infra-only revert merges without them | FIXED AND TESTED | New `infra-config-tests` job in `infra-k8s-ci.yml` runs `tests/infra` plus `infra/gateway/tests`; widened that workflow's path filters to `infra/gateway/**`, `infra/otel-collector-config.yaml`, and `tests/infra/**`. The exact pytest command runs green locally; the workflow YAML parses; a live CI run is not possible from this headless worktree |
| 7 | re-rv-3247-tests | Medium | TLS 1.3 and cipher checks pass on commented text and would pass on the pre-fix file | FIXED AND TESTED | Same fix as row 4: template-labeled assertions plus uncommented-only live-state pins |
| 8 | re-rv-3247-correct | Low | Port 80 comment says to uncomment a 301, but no 301 line exists | FIXED AND TESTED | Added the commented `return 301 https://$host$request_uri;` line with a test pinning it |
| 9 | re-rv-3247-security | Low | `_rule_covers_egress` treats missing or empty `to` (which means every destination) as a match, so a future world-open rule on these ports would still pass | FIXED AND TESTED | Helper now returns False for empty or missing `to`; all 7 current intended flows still pass because every one has a named peer; verified a synthetic world-open rule returns False |
| 10 | re-rv-3247-security | Low | No CA path knob for the Jaeger exporter; escape hatch is full plaintext | FIXED AND TESTED | Added a commented `ca_file` env knob with usage docs (kept commented so no invented path can break loads); configurability tests pin the endpoint and insecure knobs |
| 11 | re-rv-3247-tests | Low | Flow test does not compare against `containerPort`; two policies agreeing on the wrong port still pass | FIXED AND TESTED | Added a per-flow test asserting the flow port equals the callee Deployment's `containerPort` |
| 12 | re-rv-3247-tests | Low | Ingress test accepts any non-empty secretName and does not pin the issuer | FIXED AND TESTED | Same fix as row 2 |
| 13 | re-rv-3247-tests | Low | Nginx hostname tests do not read the Service manifest | FIXED AND TESTED | Same fix as row 3 (cross-check test reads every Service manifest) |
| 14 | re-rv-3247-tests | Low | OTel tests should load the file with the collector to prove env expansion | BLOCKED | No collector binary is available in this environment and network installs of it are out of scope; the consistency test parses the same `${env:NAME:-default}` expansion the collector documents, which is the closest available check |
| 15 | re-rv-3247-ops (lows) | Low | Plaintext-Jaeger export failure note; ingress fail-closed note | FIXED AND TESTED | Same fixes as rows 1 and 2 |

Skipped findings: none. Every confirmed critical, high, and medium finding above is fixed.
Pre-existing issue found but left alone (see decisions): compliance containerPort mismatch.

## Test commands and results

Exact commands run through the slot queue, with the pass and fail lines from their output:

1. `~/metacode/fleet/heavy .venv/bin/python -m pytest tests/infra infra/gateway/tests --no-cov -p no:cacheprovider`
   Result: `100 passed in 1.35s`
2. `.venv/bin/python -m ruff check tests/infra infra/gateway/tests`
   Result: `All checks passed!`
3. `.venv/bin/python -m ruff format --check` on the four touched test files
   Result: `4 files already formatted`
4. `.venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/infra-k8s-ci.yml'))"`
   Result: `workflow yaml ok`
5. `scripts/security/scan_tenant_scope.py` was not run: this change touches no queries,
   only unapplied infra configs, their tests, and CI wiring.

How the new tests were confirmed to fail without the fix (old code read via `git show HEAD:<path>`):

- OTel consistency test on HEAD config (endpoint `jaeger:4317`, insecure `false`): FAIL as required; on new config: PASS.
- `test_no_stale_container_port_upstreams` on HEAD nginx.conf: FAIL (`upstream still uses container port -service:8400`); on new: PASS. HEAD file contains all five stale tokens (`-service:8400`, `:8000`, `:8100`, `:8200`, `:8500`); new file contains none.
- `test_upstream_hosts_and_ports_match_k8s_services` on HEAD nginx.conf: FAIL (`upstream admin-service:8400 publishes no such port (Service ports: [80])`); on new: PASS.
- `test_redirect_template_line_exists`: FAIL on HEAD, PASS on new. `test_live_server_has_no_active_tls` passes on both (it is a state pin, expected).
- Tightened `_rule_covers_egress` on a synthetic world-open rule (`to: []`, port 8200): returns False (the old code returns True by falling through to the port check).
- During the fix, the new commented 301 line tripped the pre-existing whole-file `$request_uri` log-hygiene test; that test is now scoped to the `log_format` block, which is its actual intent (only the emitted log line leaks query params).

## Needs Christopher's decision

1. Compliance k8s port mismatch (pre-existing, not caused by #3247): `services/compliance/main.py` listens on 8500, but `infra/k8s/base/compliance/deployment.yaml` declares `containerPort: 8000` with Service 80 to targetPort 8000. Nginx now correctly dials Service port 80, but if the container really serves 8500 in-cluster, the Service still routes to a closed container port. Decide whether the app should listen on 8000 or the Deployment and Service should use 8500. Left untouched as out of scope.
2. Live TLS is still operator work: no certificates exist, so the 443 server stays commented and port 80 stays plaintext. The tests now pin that state honestly and tell the editor to update them when certs land. No action needed now.
3. CI choice: infra-only PRs now run the infra config tests in `infra-k8s-ci` instead of the full backend suite. If you would rather have infra-only PRs run the whole backend CI, add `infra/**` to the backend-ci and pr-gate path mirrors. Not done here to keep infra PRs cheap.
4. The `letsencrypt-prod` ClusterIssuer must be provided outside this repo before anyone applies the ingress manifest; the manifest now says so. Confirm that issuer exists wherever the manifests get applied.
