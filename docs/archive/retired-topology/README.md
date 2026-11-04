# Retired six-service topology (archive)

**Archived:** 2026-10-30, tech-debt work item WI-09 (PR #3699).
**Loaded by:** nothing. No build, test, deploy or CI workflow reads anything
under this directory. The files are kept for history and were moved with
`git mv`, so `git log --follow` reaches their earlier history.

## What this was

Before the monolith, RegEngine ran as six services (ingestion, admin,
compliance, graph, nlp, scheduler) behind an nginx gateway on Kubernetes,
with an autonomous agent "swarm" that drove development tasks. Production
today is one FastAPI process (`server/main.py`) on Railway and a Next.js app
on Vercel; `ARCHITECTURE.md` and `docs/CODEBASE_MAP.md` describe it. The
`services/*` directories are code paths inside that one process.

## Contents

| Path here | Original path | Notes |
|---|---|---|
| `k8s/base/`, `k8s/overlays/` | `infra/k8s/` | Kustomize manifests for the six deployments, ingress, network policies and monitoring. |
| `k8s/tests/` | `tests/infra/` (three files) | Tests that pinned those manifests. `tests/infra/test_otel_collector_tls.py` stayed because `infra/otel-collector-config.yaml` is still in the tree. |
| `gateway/` | `infra/gateway/` | Reference-only nginx config and its test suite. Never in the production image. |
| `swarm/regengine_swarm/` | `regengine/swarm/` | The legacy autonomous-agent runtime (about 2,800 lines), previously behind `REGENGINE_ENABLE_LEGACY_SWARM=1`. Renamed so it is not importable as `regengine.swarm`. |
| `swarm/tests/` | `tests/swarm/` | Its tests; they only exercised the runtime and the sweep script below. |
| `swarm/compliance_sweep.py` | `scripts/compliance_sweep.py` | The only importer of the runtime. |
| `workflows/infra-k8s-ci.yml` | `.github/workflows/infra-k8s-ci.yml` | Rendered the production overlay and ran the k8s and gateway tests. Removed from `scripts/workflow_inventory.txt`. |

The five narrative runbooks with a `LEGACY:` banner moved to
`docs/runbooks/legacy/` (WI-07, 2026-11-04); `scripts/check_docs_links.py`
still covers them, and their `kubectl` examples refer to the manifests now
under `k8s/`.

## Restoring something

Open an issue naming the file and the reason, then `git mv` it back and
re-add it to the relevant inventory (`pyproject.toml` `testpaths`,
`scripts/workflow_inventory.txt`, `scripts/README.md`). The supply-chain and
secrets baselines (`scripts/ci/supply_chain_baseline.json`,
`.secrets.baseline`) carried entries for the k8s manifests; those were removed
or re-pathed in the archiving PR and would need restoring too.
