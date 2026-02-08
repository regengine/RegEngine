# Security Roadmap

We're honest about what's done and what's planned. No checkmarks we haven't earned.

## Shipped (Current)

- Data encryption at rest (AES-256) — **Implemented**
- TLS 1.3 in transit — **Implemented**
- Branch protection (required reviews, no force-push to main) — **Implemented**
- CI security scanning (SAST, secrets scanning, dependency audit, DAST baseline) — **Implemented**
- Vulnerability Disclosure Policy + security.txt — **Implemented**
- Audit log export (tamper-evident, hash chain) — **Implemented**
- Hardening gates: auth + tenant isolation tests in CI — **Implemented**
- Incident response plan (internal) — **Implemented**

## Next (Q2 2026)

- OWASP ZAP authenticated scans (full flows) — **Planned**
- Third-party penetration test (API + dashboard) — **Planned**
- API rate limiting + edge protection (WAF) — **Planned**
- Container image scanning (Trivy) — **Planned**

## Next (Q3 2026)

- SSO / SAML (Scale tier) — **Planned**

## Audit Track (2026)

- SOC 2 Type II — **In Preparation**
