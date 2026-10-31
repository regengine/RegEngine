import { beforeEach, describe, expect, it } from 'vitest';
import {
  MARKETING_APP_ROUTE_PREFIXES,
  isInternalAnalyticsSession,
  isMarketingAppRoute,
  safeMarketingPath,
  shouldTrackMarketingPageview,
} from '@/lib/marketing-analytics-routes';

beforeEach(() => {
  window.history.replaceState({}, '', '/tools/ftl-checker');
  window.localStorage.removeItem('re_internal');
  document.cookie = 're_cookie_consent=; max-age=0; path=/';
});

describe('marketing pageview routes', () => {
  it('excludes each app route and its children without excluding lookalike public routes', () => {
    for (const prefix of MARKETING_APP_ROUTE_PREFIXES) {
      expect(isMarketingAppRoute(prefix)).toBe(true);
      expect(isMarketingAppRoute(`${prefix}/example`)).toBe(true);
    }
    expect(isMarketingAppRoute('/dashboarding')).toBe(false);
    expect(isMarketingAppRoute('/developers')).toBe(false);
    expect(isMarketingAppRoute('/tools/ftl-checker')).toBe(false);
  });

  it('requires accepted cookie consent and omits paths containing an email', () => {
    expect(shouldTrackMarketingPageview('/tools/ftl-checker')).toBe(false);
    document.cookie = 're_cookie_consent=declined; path=/';
    expect(shouldTrackMarketingPageview('/tools/ftl-checker')).toBe(false);

    document.cookie = 're_cookie_consent=accepted; path=/';
    expect(shouldTrackMarketingPageview('/tools/ftl-checker')).toBe(true);
    expect(shouldTrackMarketingPageview('/signup')).toBe(false);
    expect(safeMarketingPath('/tools/person%40example.com')).toBeNull();
    expect(shouldTrackMarketingPageview('/tools/person%40example.com')).toBe(false);
  });

  it('omits portal paths whose segments identify a user or record', () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    expect(safeMarketingPath('/portal/portal-123')).toBeNull();
    expect(shouldTrackMarketingPageview('/portal/portal-123')).toBe(false);
  });

  it('normalizes arbitrary public child paths so names and encoded email never become pageview URLs', () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    expect(safeMarketingPath('/pricing/Jane-Sellers')).toBe('/pricing');
    expect(safeMarketingPath('/demo')).toBe('/demo');
    expect(safeMarketingPath('/tools/person%2540example.com')).toBe('/tools');
    expect(safeMarketingPath('/Jane-Sellers')).toBeNull();
    expect(shouldTrackMarketingPageview('/pricing/Jane-Sellers')).toBe(true);
  });

  it('persists the internal marker across routes and clears it with re_internal=0', () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    expect(shouldTrackMarketingPageview('/pricing', 'https://regengine.co/pricing?re_internal=1')).toBe(false);
    expect(window.localStorage.getItem('re_internal')).toBe('1');
    expect(shouldTrackMarketingPageview('/tools/ftl-checker')).toBe(false);
    expect(isInternalAnalyticsSession('https://regengine.co/contact?re_internal=0')).toBe(false);
    expect(window.localStorage.getItem('re_internal')).toBeNull();
    expect(shouldTrackMarketingPageview('/tools/ftl-checker')).toBe(true);
  });
});
