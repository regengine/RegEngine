import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';

/**
 * SEL-585 F8: the ftl-checker page must not wrap the tool in EmailGate,
 * so the "Save your result" banner no longer shows on every tool step.
 * Results-step capture inside FTLCheckerClient stays untouched.
 */

const FRONTEND = process.cwd();

function readPage(): string {
    return fs.readFileSync(path.join(FRONTEND, 'src/app/tools/ftl-checker/page.tsx'), 'utf8');
}

describe('ftl-checker page has no EmailGate wrapper (SEL-585 F8)', () => {
    it('does not import or render EmailGate', () => {
        const source = readPage();
        expect(source).not.toMatch(/EmailGate/);
    });

    it('still renders the FTL checker client', () => {
        const source = readPage();
        expect(source).toContain('FTLCheckerClient');
        expect(source).toMatch(/<FTLCheckerClient\s*\/>/);
    });

    it('does not introduce a "Save your" banner from the page wrapper', () => {
        expect(readPage()).not.toContain('Save your');
    });
});
