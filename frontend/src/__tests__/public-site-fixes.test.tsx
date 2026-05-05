import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PricingCheckoutButton } from '@/components/billing/PricingCheckoutButton';
import { MARKETING_FOOTER_PRODUCT_LINKS } from '@/components/layout/marketing-nav';
import { EmailGate } from '@/components/tools/EmailGate';
import { ARCHIVE_EXPORT_JOBS } from '@/lib/customer-readiness';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';

const mocks = vi.hoisted(() => ({
    routerPush: vi.fn(),
    fetchWithCsrf: vi.fn(() => new Promise(() => {})),
}));

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: mocks.fetchWithCsrf,
}));

vi.mock('next/navigation', () => ({
    useRouter: () => ({
        push: mocks.routerPush,
        replace: vi.fn(),
        prefetch: vi.fn(),
        back: vi.fn(),
    }),
}));

describe('public site launch-blocker fixes', () => {
    beforeEach(() => {
        mocks.routerPush.mockClear();
        mocks.fetchWithCsrf.mockImplementation(() => new Promise(() => {}));
    });

    it('renders EmailGate children immediately while access check is pending', () => {
        render(
            <EmailGate toolName="ftl-checker">
                <h1>FTL Coverage Checker</h1>
            </EmailGate>,
        );

        expect(screen.getByRole('heading', { name: 'FTL Coverage Checker' })).toBeInTheDocument();
        expect(screen.queryByText(/checking tool access/i)).not.toBeInTheDocument();
    });

    it('renders pricing checkout anchors with signup fallbacks for every plan', () => {
        const plans = ['base', 'standard', 'premium'];

        for (const plan of plans) {
            const { unmount } = render(
                <PricingCheckoutButton tierId={plan} label={`Start ${plan}`} />,
            );

            const link = screen.getByRole('link', { name: new RegExp(`start ${plan}`, 'i') });
            expect(link).toHaveAttribute('href', `/signup?plan=${plan}&billing=annual`);
            expect(link).toHaveAttribute('data-cta-target', `/signup?plan=${plan}&billing=annual`);
            unmount();
        }
    });

    it('falls back to signup when hydrated checkout fails', async () => {
        mocks.fetchWithCsrf.mockResolvedValue({
            ok: false,
            status: 403,
            json: async () => ({ error: 'forbidden' }),
        } as Response);

        render(<PricingCheckoutButton tierId="base" label="Start Base Plan" />);

        await userEvent.click(screen.getByRole('link', { name: /start base plan/i }));

        expect(fetchWithCsrf).toHaveBeenCalledWith('/api/billing/checkout', expect.any(Object));
        expect(mocks.routerPush).toHaveBeenCalledWith('/signup?plan=base&billing=annual');
    });

    it('routes Premium to signup without attempting checkout', async () => {
        mocks.fetchWithCsrf.mockClear();
        render(<PricingCheckoutButton tierId="premium" label="Start Premium Plan" />);

        await userEvent.click(screen.getByRole('link', { name: /start premium plan/i }));

        expect(fetchWithCsrf).not.toHaveBeenCalled();
        expect(mocks.routerPush).toHaveBeenCalledWith('/signup?plan=premium&billing=annual');
    });

    it('points the public footer Get Started CTA at signup', () => {
        expect(MARKETING_FOOTER_PRODUCT_LINKS).toContainEqual({
            label: 'Get Started',
            href: '/signup',
        });
    });

    it('labels synthetic validation honestly in the footer', () => {
        expect(MARKETING_FOOTER_PRODUCT_LINKS).toContainEqual({
            label: 'Product Validation',
            href: '/case-studies',
        });
        expect(MARKETING_FOOTER_PRODUCT_LINKS).not.toContainEqual({
            label: 'Case Studies',
            href: '/case-studies',
        });
    });

    it('keeps public archive posture dates current for the demo workspace', () => {
        for (const job of ARCHIVE_EXPORT_JOBS) {
            expect(job.lastRun).not.toContain('2026-03');
            expect(job.nextRun).not.toContain('2026-03');
            expect(job.nextRun).not.toContain('2026-04');
        }
    });
});
