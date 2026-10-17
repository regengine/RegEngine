import { render, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import type React from 'react';
import { CookieBanner } from '@/components/cookie-consent/CookieBanner';
import { getConversionAttribution } from '@/lib/conversion-events';

vi.mock('@vercel/analytics/react', () => ({ Analytics: () => null }));
vi.mock('@vercel/speed-insights/next', () => ({ SpeedInsights: () => null }));
vi.mock('next/navigation', () => ({
  usePathname: () => window.location.pathname,
  useSearchParams: () => new URLSearchParams(window.location.search),
}));
vi.mock('next/link', () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

afterEach(() => {
  document.cookie = 're_cookie_consent=; max-age=0; path=/';
  window.sessionStorage.removeItem('re_utm');
  window.localStorage.removeItem('re_internal');
});

it('saves first-touch UTM tags on landing before consent and keeps them after navigation', async () => {
  window.history.replaceState({}, '', '/?utm_source=Newsletter&utm_campaign=October');
  render(<CookieBanner enableAnalytics={false} />);

  await waitFor(() => {
    expect(JSON.parse(window.sessionStorage.getItem('re_utm') ?? '{}')).toEqual({
      utm_source: 'newsletter', utm_campaign: 'october',
    });
  });

  window.history.replaceState({}, '', '/tools/ftl-checker');
  expect(getConversionAttribution()).toEqual({
    utm_source: 'newsletter', utm_campaign: 'october',
  });
});

it('detects same-path query changes before consent', async () => {
  window.history.replaceState({}, '', '/contact');
  const page = <CookieBanner enableAnalytics={false} />;
  const { rerender } = render(page);

  window.history.replaceState({}, '', '/contact?utm_source=Partner&re_internal=1');
  rerender(<CookieBanner enableAnalytics={false} />);
  await waitFor(() => {
    expect(window.sessionStorage.getItem('re_utm')).toContain('partner');
    expect(window.localStorage.getItem('re_internal')).toBe('1');
  });

  window.history.replaceState({}, '', '/contact?re_internal=0');
  rerender(<CookieBanner enableAnalytics={false} />);
  await waitFor(() => expect(window.localStorage.getItem('re_internal')).toBeNull());
});
