# Contributing to RegEngine

> **External contributions are not accepted at this time.** RegEngine is
> proprietary, source-visible software (see [LICENSE](LICENSE)). The
> repository is public for transparency and audit, not as an open-source
> project — unsolicited pull requests from outside RegEngine LLC will be
> closed without review, because merging third-party code without a
> contributor agreement is an IP problem for a proprietary codebase.
> Found a bug or security issue? Open an issue, or see [SECURITY.md](SECURITY.md).

The rest of this document is the development workflow for RegEngine LLC
engineers and authorized agents.

## Getting Started

1. **Clone** the repository
2. **Install dependencies**: see `README.md` for setup instructions
3. **Create a branch**: `git checkout -b fix/your-description`
4. **Make your changes** following the guidelines below
5. **Open a PR** against `main`

## Development Setup

```bash
# Backend (one venv at the repo root — per-service requirements.txt are deprecated, #1429)
python3 -m venv venv
source venv/bin/activate
# requirements.lock = production set (what the image installs);
# requirements-dev.lock = pytest, hypothesis, testcontainers, aiosqlite;
# requirements-experimental.lock = packages only the EXPERIMENTAL_ROUTERS need.
pip install --require-hashes -r requirements.lock -r requirements-dev.lock

# pre-commit is a dev-only tool and is deliberately NOT in requirements.in /
# requirements.lock — those are the production install set. Install it
# separately (see .pre-commit-config.yaml), outside the hash-pinned set:
pip install pre-commit
pre-commit install

pytest tests/ -v

# Frontend
cd frontend
npm install
npm run dev
```

### Running database tests locally

The RLS, migration and persistence suites need a migrated PostgreSQL and
skip without one. `pytest --require-db` (same contract as
`REGENGINE_REQUIRE_DB=1`, which the `live-db-suite` and
`seeded-migration-rehearsal` CI jobs set) turns every database-availability
skip into a failure, so a lost `DATABASE_URL` cannot turn a run green. The
guards refuse the dev-stack database itself (`regengine` / `regengine_admin`
on localhost) because the suites run `alembic upgrade head` and seed rows
into their target; point them at a scratch database on the same server:

```bash
docker compose -f docker-compose.dev.yml up -d postgres      # needs POSTGRES_PASSWORD in the environment
psql "postgresql://regengine_owner:${POSTGRES_PASSWORD}@localhost:5432/regengine" -c "CREATE DATABASE regengine_test"
export REGENGINE_MIGRATION_TEST_DB="postgresql://regengine_owner:${POSTGRES_PASSWORD}@localhost:5432/regengine_test"
DATABASE_URL="$REGENGINE_MIGRATION_TEST_DB" alembic upgrade head
python3 -m pytest tests/shared tests/migrations -q --no-cov --require-db
```

The skip message of every database gate prints the same recipe
(`tests/migrations/rls_db.py` → `skip_or_fail_without_db`). The
supplier-remediation suites under `services/ingestion/tests/*_pg.py` read
`REMEDIATION_TEST_SUPERUSER_DSN` instead (README → Testing notes).

Dependency changes go in `requirements.in` (production), `requirements-dev.in`
(test tooling) or `requirements-experimental.in` (experimental routers only),
then regenerate the locks in this order, under Python 3.11 with
`pip==24.3.1` and `pip-tools==7.5.2` as CI does:

```bash
pip-compile --allow-unsafe --generate-hashes --output-file=requirements.lock requirements.in
pip-compile --allow-unsafe --generate-hashes --output-file=requirements-dev.lock requirements-dev.in
pip-compile --allow-unsafe --generate-hashes --output-file=requirements-experimental.lock requirements-experimental.in
```

The dev and experimental files start with `-c requirements.lock`, so a package
in both resolves to the production version. CI fails if any lock is stale.

## Code Guidelines

- **Python**: Follow existing patterns. Use type hints. Lint/format with `ruff`
  (runs via pre-commit; CI enforces a `ruff check --select E9,F63,F7,F82` bug-class gate).
  - `services/shared/` carries the wider rule set in `services/shared/ruff.toml`
    (`F`, `E`, `B`, and the `S1xx`/`S3xx`/`S6xx` security rules listed there);
    backend-ci's `lint-shared` job runs `ruff check services/shared` with it.
    One more service directory adopts that file's rule set each time a PR
    touches it substantially: copy the file into the directory and fix what it
    reports in the same PR.
  - A suppression says why: `# noqa: S105 -- enum member name, not a credential`.
    A `# noqa` without a `-- reason` is unexplained debt;
    `scripts/check_noqa_ratchet.py` fails CI when the count under `services/`
    rises above `scripts/noqa_baseline.txt`, and that number only goes down.
  - `mypy services/shared` runs in backend-ci as a non-blocking report
    (`[tool.mypy]` in `pyproject.toml`); read its artifact before touching a
    typed boundary, but it does not gate a merge yet.
- **TypeScript/React**: Follow existing patterns. Run `npm run lint` and `npm run build`.
- **Commits**: Use conventional commit prefixes (`fix:`, `feat:`, `chore:`, `docs:`).
- **Tests**: Add tests for new functionality. Don't reduce coverage.
- **Security**: Never commit secrets, API keys, or credentials. Use environment variables.

## PR Process

1. Fill out the PR template completely
2. Ensure CI passes — the blocking check is the "CI Status Gate" summary job (backend + frontend)
3. Request review from a maintainer
4. Address feedback promptly

## Branch Naming

- `fix/` — bug fixes
- `feat/` — new features
- `chore/` — maintenance, dependencies, CI
- `docs/` — documentation changes

## Reporting Issues

- **Bugs**: Use the Bug Report issue template
- **Features**: Use the Feature Request issue template
- **Security**: See [SECURITY.md](SECURITY.md) — do NOT open public issues

## Code of Conduct

Be respectful, constructive, and professional in all interactions.

## License

RegEngine is proprietary software. By contributing, you agree that your
contributions become the property of RegEngine LLC under the terms of
the project license. See [LICENSE](LICENSE) for details.
