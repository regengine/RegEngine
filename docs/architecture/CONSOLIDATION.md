# Consolidation: repository shape and configured runtime

The checked-in Railway configuration selects the root
[`Dockerfile`](../../Dockerfile), which runs migrations and starts
`server.main:app` under Gunicorn/Uvicorn. This describes configuration in the
repository, not the state of any live deployment.

[`server/main.py`](../../server/main.py) composes routes and code from the
`services/` subtrees into the consolidated FastAPI application. Those directories
are code-organization boundaries, not proof of separate live deployments.
[`server/router_policy.py`](../../server/router_policy.py) controls which
optional router groups may mount. The strict production policy requires an exact
allowlist and rejects the experimental bypass; see the
[router surface audit](../engineering/ROUTER_SURFACE.md).

The minimal [`docker-compose.dev.yml`](../../docker-compose.dev.yml) supplies
PostgreSQL and Redis for local development; application processes run separately.
Other compose files, per-service Dockerfiles, and Kafka-compatible consumers
remain in the repository and may describe legacy or specialized arrangements.
Do not infer live services from them without separate deployment evidence.

For new backend routes, follow the ownership-aware inclusion and router policy
patterns in `server/main.py`, provide the operation-level security policy and
adapters required by the route manifest, and test authorization and tenant
isolation. Update root `requirements.in` and `requirements.lock` when required.
