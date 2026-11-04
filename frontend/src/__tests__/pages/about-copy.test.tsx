import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import AboutPage from '@/app/about/page';

const source = readFileSync(resolve(process.cwd(), 'src/app/about/page.tsx'), 'utf8');

describe('about page public copy', () => {
    it('addresses the reader when describing independent verification', () => {
        expect(source).toContain(
            'You can independently verify export-bundle integrity using our published verify_chain.py script.',
        );
        expect(source).not.toContain(
            'Customers can independently verify export-bundle integrity using our published verify_chain.py script.',
        );
    });

    it('scopes early tester feedback, and shows no dollar amounts (A-2169)', () => {
        expect(source).toContain(
            'No committee approvals. Early tester feedback is scoped by',
        );
        expect(source).not.toContain('Design-partner feedback is scoped to');
        expect(source).not.toContain('quarterly release trains');
        expect(source).toContain('Plans are priced per facility, and we set terms with you in a written proposal.');
        expect(source).not.toMatch(/\$\s?\d/);
        expect(source).not.toContain('$425');
    });

    it('renders the two sentences as continuous copy', () => {
        const text = render(<AboutPage />).container.textContent ?? '';

        expect(text).toContain(
            'You can independently verify export-bundle integrity using our published verify_chain.py script.',
        );
        expect(text).toContain(
            'No committee approvals. Early tester feedback is scoped by the founder and ships when the change is ready to verify, without waiting on a large release committee.',
        );
        expect(text).toContain('Plans are priced per facility, and we set terms with you in a written proposal.');
        expect(text).not.toMatch(/\$\s?\d/);
        expect(text).not.toContain('$425');
        expect(text).not.toContain('Customers can independently verify');
        expect(text).not.toContain('Design-partner feedback is scoped to');
        expect(text).not.toContain('quarterly release trains');
    });
});
