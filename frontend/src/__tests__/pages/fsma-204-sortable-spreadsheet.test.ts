import { existsSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import sitemap from '@/app/sitemap';

const read = (p: string) => readFileSync(resolve(process.cwd(), p), 'utf8');
const PAGE = 'src/app/fsma-204/sortable-spreadsheet/page.tsx';

describe('/fsma-204/sortable-spreadsheet guide', () => {
    const src = read(PAGE);

    it('answers the buyer question in the H1', () => {
        expect(src).toContain('How does a small retailer or supplier build the FSMA 204 sortable spreadsheet?');
    });

    it('links both FDA sources', () => {
        expect(src).toContain('https://www.fda.gov/media/179616/download');
        expect(src).toContain('https://www.fda.gov/media/168142/download');
    });

    it('covers the seven Critical Tracking Event tabs', () => {
        for (const tab of ['Harvesting', 'Cooling', 'Initial Packing', 'First Land-Based Receiving', 'Shipping', 'Receiving', 'Transformation']) {
            expect(src).toContain(`tab: "${tab}"`);
        }
    });

    it('ships the example workbook it links to', () => {
        expect(src).toContain('/downloads/fsma-204-sortable-spreadsheet-example.xlsx');
        const file = resolve(process.cwd(), 'public/downloads/fsma-204-sortable-spreadsheet-example.xlsx');
        expect(existsSync(file)).toBe(true);
        expect(statSync(file).size).toBeGreaterThan(0);
    });

    it('keeps to the claims rules: Beta, email only, no certification wording', () => {
        expect(src).toContain('Beta');
        expect(src).toContain('mailto:');
        expect(src).not.toMatch(/\b(compliant|certified|FDA approved|audit ready|audit-ready)\b/i);
        expect(src).not.toMatch(/\b(book a (call|demo|meeting)|schedule a (call|demo|meeting))\b/i);
    });

    it('is listed in the sitemap and linked from the FSMA 204 hub', () => {
        expect(sitemap().map((e) => e.url)).toContain('https://regengine.co/fsma-204/sortable-spreadsheet');
        expect(read('src/app/fsma-204/page.tsx')).toContain('href="/fsma-204/sortable-spreadsheet"');
    });
});
