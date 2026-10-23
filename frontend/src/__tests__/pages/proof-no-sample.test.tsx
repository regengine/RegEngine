import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ProofPage from '@/app/proof/page';

// /proof must not offer synthetic downloads or made-up hashes and sizes.
describe('/proof without sample data', () => {
    it('shows an empty state and no artifact downloads', () => {
        const { container } = render(<ProofPage />);
        const text = container.textContent ?? '';

        expect(screen.getByText(/no public artifacts are published yet/i)).toBeInTheDocument();
        expect(text).not.toMatch(/fsma-204-sample|epcis-sample|audit-bundle/i);
        expect(text).not.toMatch(/\b[0-9a-f]{12,}\b/i);
        expect(container.querySelector('a[download]')).toBeNull();
        expect(container.querySelector('a[href^="/proof/"]')).toBeNull();
        expect(container.querySelector('a[href="/verify"]')).not.toBeNull();
    });
});
