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
pip install --require-hashes -r requirements.lock

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

Dependency changes go in `requirements.in`, then regenerate the lock with
`pip-compile --allow-unsafe --generate-hashes --output-file=requirements.lock requirements.in`
(CI fails if `requirements.lock` is stale).

## Code Guidelines

- **Python**: Follow existing patterns. Use type hints. Lint/format with `ruff`
  (runs via pre-commit; CI enforces a `ruff check --select E9,F63,F7,F82` bug-class gate).
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
