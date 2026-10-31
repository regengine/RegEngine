import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const read = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8');

const PUBLIC_FILES = [
    'src/components/pricing/PricingPageClient.tsx',
    'src/app/pricing/page.tsx',
    'src/app/why-regengine/page.tsx',
    'src/app/compare/foodlogiq/page.tsx',
    'src/app/compare/tracegains/page.tsx',
    'src/app/compare/repositrak/page.tsx',
    'src/app/supplier-compliance/page.tsx',
    'src/app/tools/roi-calculator/components/ROICalculatorClient.tsx',
    'src/app/developers/page.tsx',
    'src/app/status/page.tsx',
];

// Phrases that implied RegEngine already has customers, partners, or pilots.
const RETIRED_PHRASES = [
    'for Founding Design Partners',
    'Founding Design Partners start at',
    'Founding Design Partners get preferred pricing',
    'Founding design partner rate',
    'Founding Design Partner rates from',
    'Founding Design Partner discounts',
    'What do Founding Design Partners get?',
    'Partner pricing is controlled',
    'early-design partner pricing',
    'Post-pilot list price',
    'post-pilot list pricing',
    'onboarding a limited number of partners',
    'current design-partner posture',
    'in production with founding design partners',
    'Already a customer?',
    'Pilot support',
    'pilot support',
    'during pilot programs',
];

describe('pre-revenue public copy', () => {
    it.each(PUBLIC_FILES)('%s drops phrases that imply existing customers or pilots', (file) => {
        const source = read(file);
        for (const phrase of RETIRED_PHRASES) {
            expect(source, `${file} still contains "${phrase}"`).not.toContain(phrase);
        }
    });

    it('keeps Sysco and Albertsons retailer deadlines out of buyer-programs', () => {
        const source = read('src/app/buyer-programs/page.tsx');
        expect(source).not.toContain('Albertsons');
        expect(source).not.toContain('Sysco');
    });

    it('clears stale $425 from remaining marketing pages (approved $999/$499)', () => {
        const pages = [
            'src/app/why-regengine/page.tsx',
            'src/app/buyer-programs/page.tsx',
            'src/app/supplier-compliance/page.tsx',
            'src/app/compare/foodlogiq/page.tsx',
            'src/app/compare/repositrak/page.tsx',
            'src/app/compare/tracegains/page.tsx',
        ];
        for (const file of pages) {
            const source = read(file);
            expect(source, `${file} still contains "$425"`).not.toContain('$425');
            expect(source, `${file} missing founding $499`).toContain('$499');
        }
        // Pages that state both approved figures (not the compare rows that still show $849 list)
        for (const file of [
            'src/app/why-regengine/page.tsx',
            'src/app/buyer-programs/page.tsx',
            'src/app/supplier-compliance/page.tsx',
        ]) {
            expect(read(file), `${file} missing list $999`).toContain('$999/mo per facility');
        }
    });

    it('shows no hardcoded prices on pricing surfaces', () => {
        const client = read('src/components/pricing/PricingPageClient.tsx');
        expect(client).not.toContain('$425');
        expect(client).toContain('Founding rate\n');

        const page = read('src/app/pricing/page.tsx');
        expect(page).not.toContain('$425');
        expect(page).not.toMatch(/gaMonthly: \d/);
        expect(page).toContain('Pricing is temporarily unavailable');
        expect(page).toContain('What does the Founding rate include?');
    });

    it('home page and root layout never say pre-revenue (metadata and JSON-LD included)', () => {
        for (const file of ['src/app/page.tsx', 'src/app/layout.tsx']) {
            expect(read(file), `${file} still says pre-revenue`).not.toMatch(/pre-revenue/i);
        }
    });
});
