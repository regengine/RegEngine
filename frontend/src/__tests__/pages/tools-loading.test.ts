import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';

/**
 * SEL-585 F5: /tools loading skeleton mirrors the real landing layout
 * (hero + category chips + card grid) with aria-busy, and shows no
 * sample or fake tool names while loading.
 */

const FRONTEND = process.cwd();
// Em dash or en dash, written as escapes so the source itself stays dash free.
const DASH = /[\u2014\u2013]/;

function readLoading(): string {
    return fs.readFileSync(path.join(FRONTEND, 'src/app/tools/loading.tsx'), 'utf8');
}

describe('tools loading skeleton (SEL-585 F5)', () => {
    it('announces loading with aria-busy or role=status', () => {
        const source = readLoading();
        expect(source).toMatch(/aria-busy|role=["']status["']/);
    });

    it('mirrors the landing layout with hero, chip, and grid skeleton cues', () => {
        const source = readLoading();
        expect(source).toMatch(/grid/i);
        expect(source).toMatch(/chip/i);
        expect(source).toMatch(/hero/i);
    });

    it('shows no invented tool product names or sample content', () => {
        const source = readLoading();
        for (const name of [
            'FTL List Checker',
            'CTE Mapper',
            'KDE Field Checklist',
            'TLC Format Check',
            'Self Reported Checklist',
            'Records Request Checklist',
        ]) {
            expect(source, name).not.toContain(name);
        }
        expect(source).not.toMatch(/sample|placeholder tool|lorem/i);
    });

    it('uses dash-free copy', () => {
        expect(readLoading()).not.toMatch(DASH);
    });
});
