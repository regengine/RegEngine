import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { CAPABILITY_REGISTRY, STATUS_LABELS } from '@/lib/customer-readiness';

const read = (p: string) => readFileSync(resolve(process.cwd(), p), 'utf8');

describe('#3554 empty states and hidden sample artifacts', () => {
    it('export-jobs and integrations show No data yet with CSV upload and JSON events API next steps', () => {
        for (const page of ['src/app/dashboard/export-jobs/page.tsx', 'src/app/integrations/page.tsx']) {
            const src = read(page);
            expect(src).toContain('title={NO_DATA_YET}');
            expect(src).toMatch(/href="\/ingest"/);
            expect(src).toMatch(/href="\/docs\/api"/);
        }
    });

    it('support pages render Not set for empty channel fields', () => {
        for (const page of ['src/app/settings/support/page.tsx', 'src/app/trust/support/page.tsx']) {
            const src = read(page);
            expect(src).toContain('channel.responseWindow || NOT_SET');
            expect(src).toContain('channel.notes || NOT_SET');
        }
    });

    it('labels the EPCIS capability as Preview', () => {
        const epcis = CAPABILITY_REGISTRY.find((item) => item.id === 'epcis');
        expect(epcis?.name).toBe('GS1 EPCIS 2.0 (Preview)');
        expect(epcis && STATUS_LABELS[epcis.status]).toBe('Preview');
    });

    it('no longer publishes the made-up proof samples', () => {
        expect(existsSync(resolve(process.cwd(), 'public/proof/fsma-204-sample.csv'))).toBe(false);
        expect(existsSync(resolve(process.cwd(), 'public/proof/epcis-sample.jsonld'))).toBe(false);
    });

    it('build_audit_bundle.sh requires a real export path', () => {
        let status = 0;
        let stderr = '';
        try {
            execFileSync('bash', [resolve(process.cwd(), '../scripts/build_audit_bundle.sh')], { stdio: 'pipe' });
        } catch (err) {
            const e = err as { status: number; stderr: Buffer };
            status = e.status;
            stderr = e.stderr.toString();
        }
        expect(status).not.toBe(0);
        expect(stderr).toMatch(/^usage: /);
    });
    it('hides /proof/transformation and drops every link to it', () => {
        expect(read('src/app/proof/transformation/page.tsx')).toContain('notFound()');
        expect(existsSync(resolve(process.cwd(), 'src/app/proof/transformation/opengraph-image.tsx'))).toBe(false);
        expect(read('src/app/sitemap.ts')).not.toContain('/proof/transformation');
        expect(read('src/app/walkthrough/page.tsx')).not.toContain('/proof/transformation');
    });

    it('removes the public proof zips', () => {
        for (const f of ['public/proof/audit-bundle.zip', 'public/proof/audit-bundle-tampered.zip']) {
            expect(existsSync(resolve(process.cwd(), f))).toBe(false);
        }
    });

    it('security page shows No data yet instead of illustrative verifier output', () => {
        const src = read('src/app/security/page.tsx');
        expect(src).not.toContain('Sample · illustrative');
        expect(src).toContain('title={NO_DATA_YET}');
    });

    it('CTE pages ask for the user\'s own file, not a sample', () => {
        const src = read('src/app/fsma-204/[cte]/page.tsx');
        expect(src).not.toContain('Upload a sample');
        // After merging main (#3557 retired /sandbox), the closing CTA copy comes from
        // sandboxCta().blurb, which asks for the user's own records and links /ingest.
        expect(src).toContain('{cta.blurb}');
        expect(src).not.toContain('sandbox and get an instant');
        expect(src).not.toContain('data to the sandbox');
        expect(src).toMatch(/data to\{" "\}\s*<Link href="\/ingest"[^>]*>RegEngine<\/Link>/);
    });
});
