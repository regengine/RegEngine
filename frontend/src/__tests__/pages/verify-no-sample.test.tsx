import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import VerifyPage from '@/app/verify/page';

// /verify points users at their own exported bundle. It must not hand out a
// synthetic demo bundle or show made-up manifest values.
describe('/verify without sample data', () => {
    it('has no sample bundle step, sample link, or made-up example values', () => {
        const { container } = render(<VerifyPage />);
        const text = container.textContent ?? '';

        expect(text).not.toMatch(/sample bundle/i);
        expect(text).not.toMatch(/synthetic/i);
        expect(text).not.toMatch(/grab a sample/i);
        expect(text).not.toContain('fsma-204-sample.csv');
        expect(text).not.toContain('64542033f908');
        expect(container.querySelector('a[href="/proof"]')).toBeNull();
    });

    it('sends users to export their own bundle', () => {
        render(<VerifyPage />);

        expect(screen.getByRole('link', { name: /export an audit bundle from your workspace/i })).toHaveAttribute(
            'href',
            '/dashboard/export-jobs',
        );
    });
});
