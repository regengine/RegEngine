# RegEngine – Security & Compliance Brief (Draft)

## 1. Security Posture Overview

- Hosting: the backend runs on Railway and the frontend runs on Vercel
- Structured (JSON) application logging

---

## 2. Data Handling and Segregation

- **Data Types**
  - Regulatory content (public or licensed)
  - Extracted obligations and metadata
  - Configuration and mapping data

We strongly recommend:
- No PII or sensitive customer data in non-production environments
- Using data minimization principles
- Clear separation of duties between environment access levels

---

## 3. Encryption

- **In Transit**
  - The gateway configuration sets a Strict-Transport-Security (HSTS) header

---

## 4. Access Control

- Role- and permission-based access checks
- API keys carry explicit scopes

---

## 5. Logging and Monitoring

- Structured (JSON) logging
- Prometheus metrics in the admin service

---

## 6. Regulatory Use Disclaimer

- RegEngine provides **machine-readable representations** of regulatory content and obligations.
- It does not provide legal, tax, or regulatory advice.
- Customers remain responsible for:
  - Interpreting obligations
  - Making decisions based on RegEngine outputs
  - Ensuring overall compliance with applicable laws

---

## 7. Roadmap (Security & Compliance Maturity)

- Short-term:
  - Harden environment isolation
  - Enhance incident response playbooks
  - Expand logging coverage

- Medium-term:
  - Formalize SDLC security controls
  - Third-party security assessments and penetration tests
  - SOC 2 readiness

- Long-term:
  - Certifications aligned to customer needs (e.g., ISO 27001, SOC 2)
  - Sector-specific compliance (e.g., financial services, healthcare) where relevant
