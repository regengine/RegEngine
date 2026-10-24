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

    it('keeps the published $425/mo price on pricing surfaces with the Founding rate wording', () => {
        const client = read('src/components/pricing/PricingPageClient.tsx');
        expect(client).toContain('RegEngine&apos;s Founding rate starts at $425/mo (billed annually).');
        expect(client).toContain('The Founding rate starts at $425/mo, billed annually.');
        expect(client).toContain('Founding rate\n');

        const page = read('src/app/pricing/page.tsx');
        expect(page).toContain('FSMA 204 traceability readiness from $425/mo.');
        expect(page).toContain('What does the Founding rate include?');
    });
});
