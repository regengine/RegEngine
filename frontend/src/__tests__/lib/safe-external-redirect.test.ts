import { describe, expect, it } from 'vitest';

import { isAllowedStripeCheckoutUrl } from '@/lib/safe-external-redirect';

describe('isAllowedStripeCheckoutUrl', () => {
    it('allows Stripe Checkout session URLs', () => {
        expect(isAllowedStripeCheckoutUrl('https://checkout.stripe.com/c/pay/cs_test_123')).toBe(true);
    });

    it('allows Stripe payment-link hosts', () => {
        expect(isAllowedStripeCheckoutUrl('https://buy.stripe.com/test_123')).toBe(true);
    });

    it('blocks lookalike and non-Stripe hosts', () => {
        expect(isAllowedStripeCheckoutUrl('https://checkout.stripe.com.evil.test/c/pay/x')).toBe(false);
        expect(isAllowedStripeCheckoutUrl('https://evil.test/checkout')).toBe(false);
        expect(isAllowedStripeCheckoutUrl('https://regengine.co/signup')).toBe(false);
    });

    it('blocks non-https schemes and relative paths', () => {
        expect(isAllowedStripeCheckoutUrl('http://checkout.stripe.com/c/pay/x')).toBe(false);
        expect(isAllowedStripeCheckoutUrl('javascript:alert(1)')).toBe(false);
        expect(isAllowedStripeCheckoutUrl('/signup?plan=base')).toBe(false);
    });

    it('blocks missing and unparseable values', () => {
        expect(isAllowedStripeCheckoutUrl(undefined)).toBe(false);
        expect(isAllowedStripeCheckoutUrl(null)).toBe(false);
        expect(isAllowedStripeCheckoutUrl('')).toBe(false);
        expect(isAllowedStripeCheckoutUrl(42)).toBe(false);
        expect(isAllowedStripeCheckoutUrl('https://')).toBe(false);
    });
});
