---
name: Frontend
applyTo: "frontend/**/*.{ts,tsx,js,jsx}"
description: Frontend conventions for the Next.js App Router app.
---

# RegEngine frontend rules

- Follow current Next.js App Router patterns under `frontend/src/app/`.
- Reuse existing components from `frontend/src/components/` before adding new ones.
- Keep API calls aligned with the checked-in frontend service configuration and routes.
- Use the scripts declared in `frontend/package.json` for verification.
- Prefer `npm` commands because `frontend/package-lock.json` is committed.
- Do not introduce a second package manager lockfile.
