# Consolidation: repo shape vs. deployed shape

Last verified: 2026-05-06 (tracked by [#1429](https://github.com/PetrefiedThunder/repo/issues/1429))

## TL;DR

The repo is organized as six Python "services" under `services/admin/`,
`services/ingestion/`, `services/compliance/`, `services/graph/`,
`services/nlp/`, and `services/scheduler/`. Production runs **one
consolidated FastAPI monolith** that mounts all six as routers in a
single process.

If you see a Dockerfile inside `services/<svc>/`, or a docker-compose entry
that implies a 6-port topology, or a deeper doc that still assumes six live
backend deploys, treat it as historical and cross-check against
`server/main.py` and `railway.toml` before trusting it.

## Source of truth

| What's deployed | Where to look |
|---|---|
| Build instructions | **[`Dockerfile`](../../Dockerfile)** (repo root) |
| Railway wiring | **[`railway.toml`](../../railway.toml)** — `dockerfilePath = "Dockerfile"` |
| Application entry point | **[`server/main.py`](../../server/main.py)** — mounts routers from every former microservice |
| Runtime dependencies | **[`requirements.in`](../../requirements.in)** + **[`requirements.lock`](../../requirements.lock)** (repo root) — human-edited spec plus pinned install set |

What the checked-in deploy wiring says:

- Railway builds the repo-root `Dockerfile`.
- The container starts `server.main:app`.
- No checked-in per-service Railway wiring exists in this repository.

## How the monolith mounts the old services

[`server/main.py`](../../server/main.py) imports routers from each
`services/<svc>/app/` subtree and calls `app.include_router(...)` across
ingestion / admin / graph / nlp / compliance / scheduler functionality.

The directories under `services/<svc>/` still exist because they are
**router namespaces + decomposition seams**, not deploy boundaries. The
split is preserved in the codebase so a service can be extracted back
out later if it ever makes sense.

## Vestigial scaffolding (drift surface)

These files look like they deploy services, but they don't:

| File | Status | Why it's still here |
|---|---|---|
| `services/<svc>/Dockerfile` (6 files) | **Not built in CI or deploy.** | Used only by local `docker-compose.*.yml`. Will be deleted once compose is rewritten. |
| `docker-compose.yml` / `docker-compose.prod.yml` / `docker-compose.test.yml` | **Bind to 6 ports (admin=8001, ingestion=8002, …).** | Local dev holdover. Doesn't match prod; needs rewrite (#1429 step 3). |
| `services/<svc>/Dockerfile` for scheduler | Scheduler has no deployed Dockerfile. Its logic is mounted inside the monolith via routers. | Same as above. |

Tracked and staged in **[#1429](https://github.com/PetrefiedThunder/repo/issues/1429)**.

## CI intention after the diet

Post-[#1430](https://github.com/PetrefiedThunder/repo/pull/1430):

- `Docker Build` runs once against the root Dockerfile (the image Railway ships).
- `Container Scan (Trivy)` scans the same image.
- Per-service `Lint` and `test-environment-check` matrices remain as
  isolation smoke tests — each slice under `services/<svc>/` should still
  import cleanly on its own, so bad imports get caught before they land
  in the monolith.

## Adding a new capability

Nine times out of ten, you don't add a new "service" — you add a new
router under the most-appropriate existing `services/<svc>/app/` subtree
and mount it in `server/main.py`.

Checklist:

1. Add the route module under `services/<svc>/app/<area>/`.
2. Expose a `router = APIRouter(...)` in it.
3. Add one `app.include_router(router, ...)` in [`server/main.py`](../../server/main.py).
4. If you need new deps, add them to the root `requirements.in` and refresh
   `requirements.lock`.

Do **not** create a new `services/<newsvc>/Dockerfile` unless you are
actually extracting a second deployable service — that's a Product Eng
decision, not a code-layout one.

## Historical context

- **2026-03-29** — Consolidation decision. See `server/main.py` header.
- Predating RFC: [`rfc_microservice_consolidation.md`](rfc_microservice_consolidation.md) (Q2 2026 proposal that led to the current shape).
- `ARCHITECTURE.md` now summarizes the current runtime shape and debt register.
