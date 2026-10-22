/**
 * Static guards for the developer portal.
 *
 * The portal used to be a Supabase-backed island (Next API routes, a Supabase
 * route client, sandbox `rge_test_` keys, a playground, usage charts) that no
 * backend service read. It was deleted; the portal is now one honest page on
 * the real session. These checks fail the build if any of that comes back, or
 * if something the rest of the app still needs gets deleted by mistake.
 */
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { CSRF_EXEMPT_RULES } from '@/lib/csrf';

const SRC = path.resolve(__dirname, '..');

/** All non-test source files under src (tests mention these strings on purpose). */
function sourceFiles(dir: string, out: string[] = []): string[] {
    for (const entry of readdirSync(dir)) {
        const full = path.join(dir, entry);
        if (statSync(full).isDirectory()) {
            if (entry === '__tests__') continue;
            sourceFiles(full, out);
        } else if (/\.(tsx?|jsx?|mjs|cjs|css)$/.test(entry)) {
            out.push(full);
        }
    }
    return out;
}

const read = (file: string) => readFileSync(file, 'utf8');
const rel = (file: string) => path.relative(SRC, file);

describe('developer portal static guards', () => {
    const all = sourceFiles(SRC);
    const portalFiles = sourceFiles(path.join(SRC, 'app', 'developer'));
    const developerComponentFiles = sourceFiles(path.join(SRC, 'components', 'developer'));

    it('scans a non-trivial source set (a guard over zero files passes vacuously)', () => {
        expect(all.length).toBeGreaterThan(200);
        expect(portalFiles.map(rel).sort()).toEqual(expect.arrayContaining([
            'app/developer/portal/layout.tsx',
            'app/developer/portal/page.tsx',
            'app/developer/portal/keys/page.tsx',
        ]));
        expect(developerComponentFiles.length).toBeGreaterThan(0);
    });

    it('nothing imports the deleted Supabase route client', () => {
        const offenders = all.filter((file) => read(file).includes('supabase/route-client'));
        expect(offenders.map(rel)).toEqual([]);
        expect(existsSync(path.join(SRC, 'lib', 'supabase', 'route-client.ts'))).toBe(false);
    });

    it('nothing fetches the deleted /api/developer/portal routes', () => {
        const offenders = all.filter((file) => read(file).includes('/api/developer/portal'));
        expect(offenders.map(rel)).toEqual([]);
        expect(existsSync(path.join(SRC, 'app', 'api', 'developer'))).toBe(false);
    });

    it('the portal has no sandbox keys and no SANDBOX badge', () => {
        const offenders = [...portalFiles, ...developerComponentFiles].filter((file) => {
            const text = read(file);
            return text.includes('rge_test_') || text.includes('SANDBOX');
        });
        expect(offenders.map(rel)).toEqual([]);
    });

    it('the portal does not use Supabase', () => {
        const offenders = portalFiles.filter((file) => /supabase/i.test(read(file)));
        expect(offenders.map(rel)).toEqual([]);
    });

    it('the portal layout renders the dashboard shell (the real session gate)', () => {
        const layout = read(path.join(SRC, 'app', 'developer', 'portal', 'layout.tsx'));
        expect(layout).toMatch(/import DashboardLayout from ['"]\.\.\/\.\.\/dashboard\/layout['"]/);
        expect(layout).toContain('<DashboardLayout>');
    });

    it('the portal pages make no network calls and import no data client', () => {
        for (const page of ['page.tsx', path.join('keys', 'page.tsx')]) {
            const text = read(path.join(SRC, 'app', 'developer', 'portal', page));
            expect(text, page).not.toMatch(/\bfetch\s*\(/);
            expect(text, page).not.toMatch(/fetchWithCsrf|axios|apiClient|useQuery|XMLHttpRequest/);
        }
    });

    it('nothing links to the retired /developer/login or /developer/register routes', () => {
        // Both now redirect to /login, which has no sign-up. A link to either
        // sends a prospect to a sign-in page for an account they cannot create.
        // (Comments may mention them; only quoted route strings count.)
        const offenders = all.filter((file) => /['"`]\/developer\/(register|login)\b/.test(read(file)));
        expect(offenders.map(rel)).toEqual([]);
    });

    it('the ingest page does not send customers to the Admin page or a setup wizard for a key', () => {
        // The admin key route needs a high-assurance sysadmin, and the
        // onboarding wizard has no key step. RegEngine issues live keys.
        const ingest = read(path.join(SRC, 'app', 'ingest', 'page.tsx'));
        expect(ingest).not.toMatch(/Admin page|setup wizard/i);
        expect(ingest).toMatch(/RegEngine issues live (API )?keys/);
    });

    it('the dead portal surfaces stay deleted', () => {
        const gone = [
            'app/developer/portal/playground',
            'app/developer/portal/codegen',
            'app/developer/portal/usage',
            'app/developer/portal/docs',
            'app/developer/login',
            'app/developer/register',
            'components/developer/DeveloperPortalShell.tsx',
            'components/developer/CodeBlock.tsx',
        ];
        expect(gone.filter((p) => existsSync(path.join(SRC, p)))).toEqual([]);
    });

    it('keeps what the rest of the app still uses', () => {
        // lib/supabase/admin.ts: app/actions/submit-assessment.ts.
        expect(existsSync(path.join(SRC, 'lib', 'supabase', 'admin.ts'))).toBe(true);
        expect(read(path.join(SRC, 'app', 'actions', 'submit-assessment.ts'))).toContain('@/lib/supabase/admin');
        // DocSidebar / DocPrevNext: app/docs/layout.tsx.
        const docsLayout = read(path.join(SRC, 'app', 'docs', 'layout.tsx'));
        for (const name of ['DocSidebar', 'DocPrevNext']) {
            expect(existsSync(path.join(SRC, 'components', 'developer', `${name}.tsx`)), name).toBe(true);
            expect(docsLayout, name).toContain(name);
        }
        // The portal boundary files stay.
        for (const file of ['error.tsx', 'loading.tsx']) {
            expect(existsSync(path.join(SRC, 'app', 'developer', 'portal', file)), file).toBe(true);
        }
    });

    it('no CSRF exemption covers a developer portal path', () => {
        // The portal makes no mutations. Widening the exempt list for it would
        // turn a UI gate into a CSRF hole.
        expect(JSON.stringify(CSRF_EXEMPT_RULES)).not.toMatch(/developer/i);
    });
});
