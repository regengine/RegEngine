# API Versioning Strategy

> Covers issues #944 (versioning), #946 (breaking-change policy), and #948 (changelog).

## Versioning Scheme

RegEngine uses **URL-based versioning** with the prefix `/api/v{N}/` (e.g., `/api/v1/webhooks/ingest`).

All current endpoints live under `/api/v1/` or `/v1/`. A new major version is introduced only when backward-incompatible changes cannot be avoided.

### Version Lifecycle

| Stage        | Description |
|--------------|-------------|
| **Current**  | Actively developed; receives features, fixes, and security patches. |
| **Deprecated** | Functional but frozen. Receives only critical security patches. |
| **Sunset**   | Removed from production. Requests return `410 Gone`. |

### Deprecation Timeline

1. **T-0 — Deprecation announced**: `Sunset` and `Deprecation` HTTP headers added to all responses on the deprecated version. Changelog entry published. Email notification sent to all API key holders.
2. **T + 6 months — Removal warning**: Warning response header added. Dashboard alert shown.
3. **T + 12 months — Sunset**: Version removed. Requests return `410 Gone` with a body pointing to the migration guide.

### Response Headers

Every API response includes:

```
X-RegEngine-API-Version: v1
```

Deprecated versions additionally include:

```
Deprecation: true
Sunset: Sat, 01 Jan 2028 00:00:00 GMT
Link: <https://docs.regengine.co/migration/v1-to-v2>; rel="successor-version"
```

---

## Breaking-Change Policy

### What Constitutes a Breaking Change

A change is **breaking** if it can cause a previously working integration to fail or produce incorrect results:

- Removing or renaming a field in a response body
- Removing or renaming an endpoint
- Changing the type of an existing field (e.g., string → integer)
- Adding a new **required** request parameter
- Changing authentication or authorization requirements
- Changing error response codes for existing error conditions
- Removing an enum value from an existing field

### What Is NOT a Breaking Change

- Adding a new optional field to a response body
- Adding a new optional query parameter
- Adding a new endpoint
- Adding a new enum value to a response field
- Relaxing a validation constraint (e.g., increasing max length)
- Fixing a bug where behavior did not match documentation

### Breaking-Change Process

1. **RFC**: Create an internal RFC describing the change, rationale, and migration path.
2. **Deprecation notice**: Add `Deprecated` header to affected endpoints at least **90 days** before removal.
3. **Changelog entry**: Publish a changelog entry (see `CHANGELOG.md`) describing the change and linking the migration guide.
4. **Migration guide**: Publish a guide at `/docs/migrations/` with before/after examples.
5. **Email notification**: Notify all active API key holders via email.
6. **Removal**: After the deprecation window, remove the deprecated behavior in the next major version.

---

## API Changelog

All API changes are documented in [`CHANGELOG.md`](../CHANGELOG.md) at the repo root.

### Changelog Format

Each release entry follows [Keep a Changelog](https://keepachangelog.com/) conventions:

```markdown
## [v1.x.x] — YYYY-MM-DD

### Added
- New endpoint `POST /v1/admin/tenants` for tenant onboarding

### Changed
- `GET /v1/admin/keys` now supports `X-Tenant-ID` header for filtering

### Deprecated
- `GET /v1/records` query parameter `date` — use `start_date`/`end_date` instead (removal: 2027-01-01)

### Removed
- `GET /v0/legacy-records` (sunset completed)

### Fixed
- `POST /v1/webhooks/ingest` now correctly validates GLN check digits

### Security
- API keys are now SHA-256 hashed at rest (#548)
```

### Migration Guides

Breaking changes include a migration guide at:

```
docs/migrations/v{OLD}-to-v{NEW}.md
```

Each guide contains:

- Summary of changes
- Before/after request and response examples
- SDK upgrade instructions
- Timeline and deadlines

---

## SDK Versioning

The Python SDK (`regengine` package) follows [Semantic Versioning](https://semver.org/):

- **Major**: Breaking changes to the SDK API
- **Minor**: New features, backward-compatible
- **Patch**: Bug fixes, backward-compatible

The SDK pins to a specific API version and includes a `X-RegEngine-SDK-Version` header on all requests for observability.

---

## Contact

Questions about API changes? Email [api-support@regengine.co](mailto:api-support@regengine.co) or open a GitHub issue tagged `dx`.
