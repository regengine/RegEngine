import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
    PricingCheckoutButton,
    isAllowedCheckoutUrl,
} from '@/components/billing/PricingCheckoutButton';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';

const mocks = vi.hoisted(() => ({
    routerPush: vi.fn(),
    fetchWithCsrf: vi.fn(),
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

const realLocation = window.location;

function checkoutResponse(checkoutUrl: unknown) {
    mocks.fetchWithCsrf.mockResolvedValue({
        ok: true,
        json: async () => ({ checkout_url: checkoutUrl }),
    } as Response);
}

describe('isAllowedCheckoutUrl', () => {
    it('allows Stripe hosted checkout URLs', () => {
        expect(isAllowedCheckoutUrl('https://checkout.stripe.com/c/pay/cs_test_123')).toBe(true);
        expect(isAllowedCheckoutUrl('https://buy.stripe.com/test_123')).toBe(true);
    });

    it('is case-insensitive on the hostname', () => {
        expect(isAllowedCheckoutUrl('https://CHECKOUT.STRIPE.COM/c/pay/cs_test_123')).toBe(true);
    });

    it('rejects non-Stripe hosts, even lookalikes', () => {
        expect(isAllowedCheckoutUrl('https://evil.example.com/steal')).toBe(false);
        expect(isAllowedCheckoutUrl('https://checkout.stripe.com.evil.com/pay')).toBe(false);
        expect(isAllowedCheckoutUrl('https://evilstripe.com/pay')).toBe(false);
    });

    it('rejects non-HTTPS, relative and non-URL values', () => {
        expect(isAllowedCheckoutUrl('http://checkout.stripe.com/c/pay/cs_test_123')).toBe(false);
        expect(isAllowedCheckoutUrl('/signup?plan=base')).toBe(false);
        expect(isAllowedCheckoutUrl('javascript:alert(1)')).toBe(false);
        expect(isAllowedCheckoutUrl('')).toBe(false);
        expect(isAllowedCheckoutUrl(undefined)).toBe(false);
        expect(isAllowedCheckoutUrl(null)).toBe(false);
    });
});

describe('PricingCheckoutButton checkout redirect', () => {
    beforeEach(() => {
        mocks.routerPush.mockClear();
        mocks.fetchWithCsrf.mockReset();
        Object.defineProperty(window, 'location', {
            value: { href: 'http://localhost/' },
            writable: true,
            configurable: true,
        });
    });

    afterEach(() => {
        Object.defineProperty(window, 'location', {
            value: realLocation,
            writable: true,
            configurable: true,
        });
    });

    it('redirects to a Stripe checkout URL from the backend', async () => {
        checkoutResponse('https://checkout.stripe.com/c/pay/cs_test_123');

        render(<PricingCheckoutButton tierId="base" label="Start Base Plan" />);
        await userEvent.click(screen.getByRole('link', { name: /start base plan/i }));

        await waitFor(() =>
            expect(window.location.href).toBe('https://checkout.stripe.com/c/pay/cs_test_123'),
        );
        expect(mocks.routerPush).not.toHaveBeenCalled();
    });

    it('does not redirect to a non-Stripe checkout URL', async () => {
        checkoutResponse('https://evil.example.com/steal-session');

        render(<PricingCheckoutButton tierId="base" label="Start Base Plan" />);
        await userEvent.click(screen.getByRole('link', { name: /start base plan/i }));

        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent(/stripe checkout was unavailable/i);
        expect(window.location.href).toBe('http://localhost/');
        expect(mocks.routerPush).not.toHaveBeenCalled();
    });

    it('does not redirect when checkout_url is missing', async () => {
        mocks.fetchWithCsrf.mockResolvedValue({
            ok: true,
            json: async () => ({}),
        } as Response);

        render(<PricingCheckoutButton tierId="base" label="Start Base Plan" />);
        await userEvent.click(screen.getByRole('link', { name: /start base plan/i }));

        const alert = await screen.findByRole('alert');
        expect(alert).toHaveTextContent(/stripe checkout was unavailable/i);
        expect(window.location.href).toBe('http://localhost/');
    });
});
