/**
 * Allowlist for Stripe Checkout redirects.
 *
 * The backend creates the Checkout session and returns its URL, but the
 * client still validates before leaving the app: a compromised or buggy
 * backend response must not turn the pricing button into an open redirect
 * to an attacker-controlled page.
 */

/** Exact hosts Stripe serves Checkout and Payment Links from. */
const STRIPE_CHECKOUT_HOSTS = new Set(['checkout.stripe.com', 'buy.stripe.com']);

/**
 * True when `candidate` is an https URL on a Stripe checkout host.
 * Rejects anything else: relative paths, other schemes, other hosts
 * (including lookalikes such as checkout.stripe.com.evil.test), and
 * unparseable input.
 */
export function isAllowedStripeCheckoutUrl(candidate: unknown): boolean {
    if (typeof candidate !== 'string' || candidate.length === 0) return false;
    let url: URL;
    try {
        url = new URL(candidate);
    } catch {
        return false;
    }
    if (url.protocol !== 'https:') return false;
    return STRIPE_CHECKOUT_HOSTS.has(url.hostname.toLowerCase());
}
