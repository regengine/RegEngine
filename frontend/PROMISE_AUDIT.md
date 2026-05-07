# Promise Audit

Run `npm run promise:audit` before deploys and in CI.

What it checks:
- banned dead-host and overclaim strings in `src/`
- critical internal routes still exist in `src/app`
- critical external URLs still return a non-error HTTP status

Current banned strings include:
- `status.regengine.co`
- `slack.regengine.co`
- `api.regengine.co`
- `cal.com/regengine`
- `Start Free Trial`
- `14-day free trial`
- `Get API Access`
- `community Slack`

Notes:
- Set `PROMISE_AUDIT_SKIP_EXTERNAL=1` to skip live external URL fetches.
- Keep the critical route and URL allowlists in `scripts/promise-audit.mjs` small and intentional.
