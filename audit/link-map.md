# Link Map Audit

Post-remediation static scan run against `frontend/src/app/**/*.tsx` and `frontend/public/**`.

- Internal links scanned: **291**
- Broken internal links detected: **0**

## Validation Notes

- `/ftl-checker`, `/contact`, `/demo`, `/resources/calculators`, and `/api-reference/energy` now resolve.
- `/sdk/verify_chain.py` now resolves from `frontend/public/sdk/verify_chain.py`.
- Previously missing docs subpaths are covered by `frontend/src/app/docs/[...slug]/page.tsx`.
- No unresolved `href="/..."` links were detected in route pages.
