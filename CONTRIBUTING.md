# Contributing to RegEngine

Thank you for your interest in contributing. This document covers the conventions and requirements for getting code merged.

## Branch Naming

All branches must follow this pattern:

```
<type>/<short-description>
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

Examples:
- `feat/supplier-bulk-upload`
- `fix/redis-session-ttl`
- `docs/api-reference-update`

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
```

Scopes map to service or directory names: `admin`, `compliance`, `graph`, `ingestion`, `nlp`, `scheduler`, `frontend`, `kernel`, `infra`.

Examples:
- `feat(frontend): add supplier onboarding wizard`
- `fix(admin): correct refresh token expiry logic`
- `test(compliance): add coverage for score model edge cases`

## Pull Request Requirements

1. **CI must pass.** The `CI Status Gate` job on both `backend-ci` and `frontend-ci` workflows blocks merges on failure.
2. **Tests required for new behavior.** If your PR adds or changes functionality, include tests.
3. **One logical change per PR.** Avoid bundling unrelated fixes.
4. **Write a clear PR description.** Explain *what* changed and *why*.

## Running CI Locally

Backend (run from repo root):

```bash
cd services/<service>
pip install -r requirements.txt
pip install pytest pytest-cov pytest-asyncio httpx
pytest tests/ -v --cov=app
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run test:run
npm run build
```

All four commands must pass before submitting a PR that touches frontend code.

## Sensitive Areas

Changes to these areas require extra scrutiny. Tag a maintainer for review.

| Area | Why it matters | Key paths |
|---|---|---|
| Auth / sessions | Token handling, session persistence, JWT signing | `services/admin/app/auth/`, `frontend/src/app/api/admin/` |
| Audit logging | Immutable event stream — must not drop or alter events | `services/admin/app/audit/`, `shared/audit/` |
| Row-level security | Tenant isolation at the database layer | `migrations/rls_*.sql` |
| Database migrations | Schema changes affect all environments | `migrations/` |
| Hash-chain evidence | Tamper-evidence integrity — hash ordering is critical | `kernel/evidence/` |
| Multi-tenant middleware | Tenant context injection across all services | `shared/middleware/` |

## Code Style

- **Python:** Black (line-length 120), isort (black profile), flake8. See `pyproject.toml`.
- **TypeScript/JS:** ESLint config in `frontend/`. Run `npm run lint`.
- Keep line length at 120 for Python files.

## What We Are Not Accepting Right Now

To keep execution focused on the FSMA 204 wedge:

- **New vertical modules** (e.g., SOX, HIPAA, NERC CIP) — the compliance library specs exist in `docs/specs/` and `docs/compliance/ingestion_library/` but are not being actively developed.
- **Major architectural changes** — the current service topology is intentionally stable.
- **Marketing site redesigns** — the marketing surface is locked for the current GTM push.

If you want to propose work in one of these areas, open an issue first to discuss scope and timing.

## Getting Help

Open an issue or reach out to the maintainers directly. For security issues, see `docs/security/VDP.md`.
