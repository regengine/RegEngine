# RegEngine Frontend

Next.js 16 interface for RegEngine's FSMA 204 food traceability evidence platform. Operators import supplier data, review traceability records and compliance gaps, and prepare audit/export workflows. Public pages explain the product and expose synthetic proof artifacts.

See the [product description](../docs/PRODUCT_DESCRIPTION.md) for capability availability and the [root README](../README.md) for backend setup. UI routes alone do not establish that the associated backend feature is enabled; the [production router policy](../server/router_policy.py) controls API exposure.

## Product surfaces

| Surface | Source |
| --- | --- |
| Dashboard and operational views | [dashboard](src/app/dashboard/) |
| CSV intake, import results, and optional Jev column/CTE suggestions | [ingest](src/app/ingest/), [CTE suggestion prompt](src/components/fsma/CteSuggestionPrompt.tsx) |
| Traceability records, compliance, and exception review | [records](src/app/records/), [compliance](src/app/compliance/), [exceptions](src/app/exceptions/) |
| Supplier preflight portal | [portal](src/app/portal/) |
| Buyer manifest remediation and correction actions | [remediation](src/app/remediation/) — requires the remediation API, which is excluded from the production allowlist |
| Recall reporting and audit views | [recall report](src/app/dashboard/recall-report/), [audit](src/app/audit/) |
| Email-code/passkey login, invitations, and API keys | [login](src/app/login/), [invite acceptance](src/app/accept-invite/), [API keys](src/app/api-keys/) |
| Bundle verification and recall drill | [verify](src/app/verify/), [recall drills](src/app/dashboard/recall-drills/) |
| Product documentation and developer portal | [docs](src/app/docs/), [developer portal](src/app/developer/portal/) |

Jev assistance is optional. Suggestions are visible for review; automatic application defaults off. See the [Jev guide](../docs/engineering/JEV_HEADER_MAPPING.md) for configuration, evidence, and data-sharing defaults.

## Stack

Next.js App Router, React, TypeScript, Tailwind CSS, TanStack Query, Vitest, and Playwright. Exact dependencies and available scripts are in [package.json](package.json); npm uses the checked-in [package-lock.json](package-lock.json).

## Local development

Use the Node version pinned in [../.nvmrc](../.nvmrc) and npm. Start the consolidated FastAPI backend and PostgreSQL/Redis using the [root setup](../README.md#local-development).

From this directory:

```bash
npm ci
INGESTION_SERVICE_URL=http://localhost:8000 \
ADMIN_SERVICE_URL=http://localhost:8000 \
COMPLIANCE_SERVICE_URL=http://localhost:8000 \
GRAPH_SERVICE_URL=http://localhost:8000 \
NLP_SERVICE_URL=http://localhost:8000 \
npm run dev
```

Open [localhost:3000](http://localhost:3000). These service names route to the same backend process; they do not require separate deployments. Setting a URL does not enable an experimental backend router. Authentication and protected workflows also require tenant/user provisioning and the appropriate backend configuration.

Keep credentials in the approved local credential store, outside tracked files. Never place secrets in `NEXT_PUBLIC_*` variables: those are exposed to the browser.

## Validation

```bash
npm run lint
npm run test:run
npm run build
```

`lint` runs ESLint and design lint. `build` also surfaces TypeScript errors; there is no `typecheck` script. End-to-end checks use `npm run test:e2e` and require the environment specified by the relevant Playwright configuration.

## API routing and deployment

Browser requests use same-origin Next.js API proxies. Server-side upstream resolution lives in [api-config.ts](src/lib/api-config.ts), with routing/build configuration in [next.config.js](next.config.js). The frontend deploys separately to Vercel; the backend is one Railway application. Configure upstream URLs for the target environment before using authenticated workflows.

The [frontend CI workflow](https://github.com/regengine/RegEngine/blob/main/.github/workflows/frontend-ci.yml) defines automated validation. Build success does not establish that live login, ingestion, or exports work against a deployed backend.

## License

Proprietary, source-visible software under the root [LICENSE](../LICENSE). The public bundle verifier at [public/sdk/verify_chain.py](public/sdk/verify_chain.py) is covered by that license's Apache 2.0 exception.
