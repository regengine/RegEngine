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

    it('scopes early tester feedback, and keeps the published price', () => {
        expect(source).toContain(
            'No committee approvals. Early tester feedback is scoped to',
        );
        expect(source).not.toContain('Design-partner feedback is scoped to');
        expect(source).toContain('$425/mo');
    });

    it('renders the two sentences as continuous copy', () => {
        const text = render(<AboutPage />).container.textContent ?? '';

        expect(text).toContain(
            'You can independently verify export-bundle integrity using our published verify_chain.py script.',
        );
        expect(text).toContain(
            'No committee approvals. Early tester feedback is scoped to ship within days, not quarters.',
        );
        expect(text).toContain('$425/mo');
        expect(text).not.toContain('Customers can independently verify');
        expect(text).not.toContain('Design-partner feedback is scoped to');
    });
});
