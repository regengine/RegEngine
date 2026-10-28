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

    it('pricing surfaces take prices only from the approved terms module', () => {
        const client = read('src/components/pricing/PricingPageClient.tsx');
        expect(client).toContain("from '@/lib/pricing-terms'");
        expect(client).not.toMatch(/tier\.(gaAnnual|gaMonthly|partnerAnnual|partnerMonthly)/);
        expect(client).not.toContain('50% off');
        expect(client).not.toMatch(/annual billing/i);

        const page = read('src/app/pricing/page.tsx');
        expect(page).toContain("from '@/lib/pricing-terms'");
        expect(page).not.toMatch(/gaMonthly: \d/);
        expect(page).toContain('How does the pilot work?');
    });

    it('approved terms module carries the A-2155 prices and pilot terms', () => {
        const terms = read('src/lib/pricing-terms.ts');
        expect(terms).toContain("'$999 per month, per facility'");
        expect(terms).toContain("'$499 per month, per facility'");
        expect(terms).toContain("'$2,000 for 90 days on 1 facility'");
        expect(terms).toContain("'$1,500 if you convert to a subscription within 30 days'");
        expect(terms).toContain('credited toward your first subscription invoice');
    });

    it.each([
        ...PUBLIC_FILES,
        'src/app/about/page.tsx',
        'src/app/buyer-programs/page.tsx',
        'src/lib/pricing-terms.ts',
    ])('%s carries no stale prices, retailer deadlines, or billed-annually terms', (file) => {
        const source = read(file);
        for (const stale of ['$425', '$849', '$850', '$549', '$1,099', '$639', '$1,275', 'billed annually']) {
            expect(source, `${file} still contains "${stale}"`).not.toContain(stale);
        }
        expect(source).not.toMatch(/sysco|albertsons/i);
    });

    it('home page and root layout never say pre-revenue (metadata and JSON-LD included)', () => {
        for (const file of ['src/app/page.tsx', 'src/app/layout.tsx']) {
            expect(read(file), `${file} still says pre-revenue`).not.toMatch(/pre-revenue/i);
        }
    });
});
