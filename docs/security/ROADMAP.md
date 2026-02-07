# Security Roadmap

We're honest about what's done and what's planned. No checkmarks we haven't earned.

## Shipped (Current)

- Data encryption at rest (AES-256) — **Implemented**
- TLS 1.3 in transit — **Implemented**
- Branch protection (required reviews, no force-push to main) — **Implemented**

## Shipping Tonight

- CI security scanning (SAST, secrets scanning, dependency audit, DAST baseline) — **Implementing**
- Vulnerability Disclosure Policy + security.txt — **Implementing**
- Audit log export (tamper-evident) — **Implementing**
- Hardening gates: auth + tenant isolation tests in CI — **Implementing**
- Incident response plan (internal) — **Implementing**

## Next (Q2 2026)

- OWASP ZAP authenticated scans (full flows) — **Planned**
- Third-party penetration test (API + dashboard) — **Planned**
- SSO / SAML (Scale tier) — **In Progress**
- API rate limiting + edge protection (WAF) — **Planned**
- Container image scanning (Trivy) — **Planned**

## Audit Track (2026)

- SOC 2 Type II — **In Preparation**
