import { afterEach, describe, expect, it } from 'vitest';

import { getStoredConsent, setConsentCookie } from '@/lib/cookie-consent';

describe('cookie consent helpers', () => {
    afterEach(() => {
        document.cookie = 're_cookie_consent=; max-age=0; path=/';
    });

    it('returns null before any choice is stored', () => {
        expect(getStoredConsent()).toBeNull();
    });

    it('round-trips an accepted choice', () => {
        setConsentCookie('accepted');
        expect(getStoredConsent()).toBe('accepted');
    });

    it('round-trips a declined choice', () => {
        setConsentCookie('declined');
        expect(getStoredConsent()).toBe('declined');
    });

    it('ignores unexpected cookie values instead of trusting them', () => {
        document.cookie = 're_cookie_consent=maybe; path=/';
        expect(getStoredConsent()).toBeNull();
    });
});
