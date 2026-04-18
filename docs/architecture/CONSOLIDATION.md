# Consolidation: repo shape vs. deployed shape

Last verified: 2026-04-18 (tracked by [#1429](https://github.com/PetrefiedThunder/repo/issues/1429))

## TL;DR

The repo is organized as six Python "services" under `services/admin/`,
`services/ingestion/`, `services/compliance/`, `services/graph/`,
`services/nlp/`, and `services/scheduler/`. Production runs **one
consolidated FastAPI monolith** that mounts all six as routers in a
single process.

If you see a Dockerfile inside `services/<svc>/`, or a per-service
`requirements.txt`, or a docker-compose entry that implies a 6-port
topology — treat it as historical and cross-check against `server/main.py`
and `railway.toml` before trusting it.

## Source of truth

| What's deployed | Where to look |
|---|---|
| Build instructions | **[`Dockerfile`](../../Dockerfile)** (repo root) |
| Railway wiring | **[`railway.toml`](../../railway.toml)** — `dockerfilePath = "Dockerfile"` |
| Application entry point | **[`server/main.py`](../../server/main.py)** — mounts 66 routers from every former microservice |
| Runtime dependencies | **[`requirements.txt`](../../requirements.txt)** (repo root) — single source of truth |
| Prod URL | `https://regengine-production.up.railway.app` |

What's actually running:

```
$ curl https://regengine-production.up.railway.app/
{"service":"RegEngine API","version":"1.0.0","mode":"consolidated"}
```

Railway topology: 1 monolith service + neo4j + Redis. No per-service
deploys.

## How the monolith mounts the old services

[`server/main.py`](../../server/main.py) imports routers from each
`services/<svc>/app/` subtree and calls `app.include_router(...)` on each
one. Counting: **66** `include_router` calls as of this write, spanning
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
| `services/<svc>/requirements.txt` (6 files) | **Header says "DEPRECATED — use root requirements.txt".** | Kept for anyone running `cd services/<svc> && pip install -r requirements.txt` locally. |
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
4. If you need new deps, add them to the root `requirements.txt`.

Do **not** create a new `services/<newsvc>/Dockerfile` unless you are
actually extracting a second deployable service — that's a Product Eng
decision, not a code-layout one.

## Historical context

- **2026-03-29** — Consolidation decision. See `server/main.py` header.
- Predating RFC: [`rfc_microservice_consolidation.md`](rfc_microservice_consolidation.md) (Q2 2026 proposal that led to the current shape).
- ARCHITECTURE.md (last updated 2026-03-28) still depicts the 6-service
  topology diagram. Accurate for code boundaries, out of date for the
  deployed shape. Read it alongside this doc.
