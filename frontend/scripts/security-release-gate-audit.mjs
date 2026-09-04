import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const spec = readFileSync(resolve('tests/e2e/security-release-gate.spec.ts'), 'utf8');
const workflow = readFileSync(resolve('../.github/workflows/frontend-ci.yml'), 'utf8');

const forbidden = [
    [/\btest\.(?:skip|fixme|fail)\b/, 'skip/fixme/fail marker'],
    [/\.catch\(\(\) => null\)/, 'optional assertion fallback'],
    [/\bexpect\.soft\b/, 'soft-only assertion'],
];

for (const [pattern, label] of forbidden) {
    if (pattern.test(spec)) {
        throw new Error(`Security Playwright release gate contains a forbidden ${label}`);
    }
}

if (!workflow.includes('tests/e2e/security-release-gate.spec.ts')) {
    throw new Error('frontend-ci.yml does not execute the Security Playwright release gate');
}

const retiredAnonymousBffs = [
    'src/app/api/alpha-signup/route.ts',
    'src/app/api/fsma/customer-readiness/export-jobs/route.ts',
    'src/app/api/fsma/customer-readiness/mappings/route.ts',
    'src/app/api/fsma/customer-readiness/recall-drills/route.ts',
];
for (const path of retiredAnonymousBffs) {
    if (existsSync(resolve(path))) {
        throw new Error(`Release-disabled anonymous BFF was reintroduced: ${path}`);
    }
}

const retiredBffPaths = [
    '/api/fsma/customer-readiness/export-jobs',
    '/api/fsma/customer-readiness/mappings',
    '/api/fsma/customer-readiness/recall-drills',
];
for (const page of [
    'src/app/dashboard/export-jobs/page.tsx',
    'src/app/dashboard/integrations/page.tsx',
    'src/app/dashboard/recall-drills/page.tsx',
]) {
    const source = readFileSync(resolve(page), 'utf8');
    for (const path of retiredBffPaths) {
        if (source.includes(path)) {
            throw new Error(`${page} calls retired anonymous BFF ${path}`);
        }
    }
}

const credentialedServerFetches = [
    'src/app/api/billing/checkout/route.ts',
    'src/app/api/contact/route.ts',
    'src/app/api/nlp/ask/route.ts',
    'src/app/api/proxy/route.ts',
    'src/app/api/session/route.ts',
    'src/app/api/tools/verify/route.ts',
    ...[
        'status/[tenantId]/route.ts',
        'snapshots/[tenantId]/route.ts',
        'snapshots/[tenantId]/diff/route.ts',
        'snapshots/[tenantId]/[snapshotId]/attest/route.ts',
        'snapshots/[tenantId]/[snapshotId]/audit-pack/route.ts',
        'snapshots/[tenantId]/[snapshotId]/export/route.ts',
        'snapshots/[tenantId]/[snapshotId]/fda-response/route.ts',
        'snapshots/[tenantId]/[snapshotId]/refreeze/route.ts',
        'snapshots/[tenantId]/[snapshotId]/verify/route.ts',
    ].map((path) => `src/app/api/v1/compliance/${path}`),
];
for (const path of credentialedServerFetches) {
    const source = readFileSync(resolve(path), 'utf8');
    if (source.includes('fetch(') && !/redirect:\s*['"]manual['"]/.test(source)) {
        throw new Error(`Credentialed server fetch can follow redirects: ${path}`);
    }
}

console.log('Security Playwright release-gate audit passed.');
