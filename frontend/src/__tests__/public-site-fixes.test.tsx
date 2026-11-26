import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PricingCheckoutButton } from '@/components/billing/PricingCheckoutButton';
import { MARKETING_FOOTER_PRODUCT_LINKS } from '@/components/layout/marketing-nav';
import { EmailGate } from '@/components/tools/EmailGate';
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

/**
 * jsdom does not implement navigation, so assigning window.location.href is
 * unobservable. Swap in a plain stub that records the assignment, then
 * restore the real location after each test.
 */
function stubLocationHref() {
    const realLocation = window.location;
    const stub = { href: realLocation.href };
    Object.defineProperty(window, 'location', {
        configurable: true,
        writable: true,
        value: stub,
    });
    return stub;
}

describe('public site launch-blocker fixes', () => {
    const realLocation = window.location;

    beforeEach(() => {
        mocks.routerPush.mockClear();
        mocks.fetchWithCsrf.mockImplementation(() => new Promise(() => {}));
    });

    afterEach(() => {
        Object.defineProperty(window, 'location', {
            configurable: true,
            writable: true,
            value: realLocation,
        });
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

        // Per PR #2175/#2211: on 403/non-OK, the component surfaces an honest
        // error message instead of silently pushing to signup. The user must
        // explicitly click "Continue to signup" to navigate.
        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent(/stripe checkout was unavailable/i);
        expect(mocks.routerPush).not.toHaveBeenCalled();

        await userEvent.click(screen.getByRole('button', { name: /continue to signup/i }));
        expect(mocks.routerPush).toHaveBeenCalledWith('/signup?plan=base&billing=annual');
    });

    it('redirects to Stripe Checkout when the backend URL is allowlisted', async () => {
        mocks.fetchWithCsrf.mockResolvedValue({
            ok: true,
            json: async () => ({ checkout_url: 'https://checkout.stripe.com/c/pay/cs_test_123' }),
        } as Response);
        const locationStub = stubLocationHref();

        render(<PricingCheckoutButton tierId="base" label="Start Base Plan" />);

        await userEvent.click(screen.getByRole('link', { name: /start base plan/i }));

        await waitFor(() => {
            expect(locationStub.href).toBe('https://checkout.stripe.com/c/pay/cs_test_123');
        });
        expect(screen.queryByRole('alert')).toBeNull();
    });

    it('blocks a non-Stripe checkout URL instead of redirecting', async () => {
        mocks.fetchWithCsrf.mockResolvedValue({
            ok: true,
            json: async () => ({ checkout_url: 'https://checkout.stripe.com.evil.test/phish' }),
        } as Response);
        const locationStub = stubLocationHref();
        const hrefBefore = locationStub.href;

        render(<PricingCheckoutButton tierId="base" label="Start Base Plan" />);

        await userEvent.click(screen.getByRole('link', { name: /start base plan/i }));

        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent(/stripe checkout was unavailable/i);
        expect(locationStub.href).toBe(hrefBefore);
        expect(mocks.routerPush).not.toHaveBeenCalled();
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

    it('keeps the hidden case-studies route out of the footer', () => {
        expect(MARKETING_FOOTER_PRODUCT_LINKS.map((link) => link.href)).not.toContain('/case-studies');
    });
});
