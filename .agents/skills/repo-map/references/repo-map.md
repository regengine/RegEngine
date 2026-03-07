# RegEngine quick repo map

## Top-level areas

- `services/` — backend services and `services/shared/`
- `frontend/` — Next.js 15 app
- `docs/` — setup guides, specs, security, deployment, product docs
- `scripts/` — smoke tests, swarm helpers, verification scripts
- `.agent/` — legacy swarm-script prompts and personas
- `.agents/` — editor-facing compatibility layer for rules/workflows/skills

## Existing services

- `admin`
- `billing`
- `compliance`
- `devops`
- `energy`
- `graph`
- `ingestion`
- `nlp`
- `opportunity`
- `scheduler`
- `shared`

## Common verification commands

From repo root:
- `python -m pytest tests -q`
- `python -m pytest services/<service>/tests -q`
- `bash scripts/test-all.sh --quick`

From `frontend/`:
- `npm install`
- `npm run lint`
- `npm run test:run`
- `npm run build`
