# Frontend Page Audit — 2026-03-19

## Summary
- **Total pages**: 143 (before cleanup)
- **Moved to `_disabled/`**: 7 genuinely orphaned directories
- **Recommended core pages**: ~20 for design partner journey

## Moved to `src/app/_disabled/` (unreachable from any nav)
| Directory | Reason |
|-----------|--------|
| `about/` | Marketing page — no link from any nav |
| `get-started/` | Duplicate of onboarding — no link |
| `design-partner/` | Orphaned — no link from any page |
| `founding-design-partners/` | Orphaned — no link from any page |
| `checkout/` | Future billing — not wired to anything |
| `walkthrough/` | Orphaned tutorial — replaced by onboarding |
| `mobile/` | Mobile capture — not linked; `/dashboard/scan` is the active version |

## Candidates for Future Archival (still reachable but unused by partners)
| Route | Notes |
|-------|-------|
| `/owner/*` (15 pages) | Billing/contracts suite — future feature, no partner usage |
| `/developer/portal/*` (11 pages) | Developer docs — only for API consumers |
| `/compliance/*` (6 pages) | Root-level compliance — `/dashboard/compliance` is the active version |
| `/settings/*` (5 pages) | Root-level settings — `/dashboard/settings` is the active version |
| `/tools/*` (20 pages) | Many tools are SEO-oriented — keep but deprioritize maintenance |
| `/trust/*` (4 pages) | Trust center — keep for diligence |

## Core Design Partner Journey (keep and maintain)
1. `/` — Landing page
2. `/alpha` — Signup
3. `/login` — Login
4. `/onboarding` + `/onboarding/bulk-upload` — Onboarding wizard
5. `/dashboard` — Main dashboard
6. `/dashboard/heartbeat` — System health
7. `/dashboard/compliance` — Compliance score
8. `/dashboard/alerts` — Alerts
9. `/dashboard/recall-report` — Recall readiness
10. `/dashboard/recall-drills` — Mock drills
11. `/dashboard/export-jobs` — FDA export
12. `/dashboard/scan` — Field capture
13. `/dashboard/receiving` — Receiving dock
14. `/dashboard/integrations` — Integrations
15. `/dashboard/suppliers` — Suppliers
16. `/dashboard/products` — Products
17. `/dashboard/team` — Team
18. `/dashboard/settings` — Settings
19. `/dashboard/notifications` — Notifications
20. `/dashboard/audit-log` — Audit log
