import { describe, expect, it } from 'vitest';
import { isAuthenticatedAppRoute, shouldHideMarketingChrome } from '@/lib/app-routes';

describe('app route ownership', () => {
    it('treats operational root routes as authenticated app routes', () => {
        expect(isAuthenticatedAppRoute('/rules')).toBe(true);
        expect(isAuthenticatedAppRoute('/records/evt_123')).toBe(true);
        expect(isAuthenticatedAppRoute('/compliance/profile')).toBe(true);
    });

    it('does not hide marketing chrome on public tools or docs', () => {
        expect(shouldHideMarketingChrome('/tools/data-import')).toBe(false);
        expect(shouldHideMarketingChrome('/docs/api')).toBe(false);
    });

    it('hides marketing chrome on authenticated app and field capture routes', () => {
        expect(shouldHideMarketingChrome('/dashboard')).toBe(true);
        expect(shouldHideMarketingChrome('/settings/security')).toBe(true);
        expect(shouldHideMarketingChrome('/mobile/capture')).toBe(true);
    });
});
