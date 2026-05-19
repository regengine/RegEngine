import { renderToStaticMarkup } from 'react-dom/server';
import type { PropsWithChildren } from 'react';
import { describe, expect, it, vi } from 'vitest';

const headersMock = vi.hoisted(() => vi.fn());

vi.mock('next/headers', () => ({
    headers: headersMock,
}));

vi.mock('@/lib/providers', () => ({
    Providers: ({ children, nonce }: PropsWithChildren<{ nonce?: string }>) => (
        <div data-provider-nonce={nonce ?? ''}>{children}</div>
    ),
}));

vi.mock('@/components/layout/marketing-header', () => ({
    MarketingHeader: () => <header>Marketing header</header>,
}));

vi.mock('@/components/layout/auth-aware-footer', () => ({
    AuthAwareFooter: () => <footer>Auth footer</footer>,
}));

vi.mock('@/components/accessibility/AccessibilityWidget', () => ({
    AccessibilityWidget: () => <div>Accessibility widget</div>,
}));

vi.mock('@/components/cookie-consent/CookieBanner', () => ({
    CookieBanner: () => <div>Cookie banner</div>,
}));

vi.mock('@/components/seo/json-ld', () => ({
    JSONLD: () => <script type="application/ld+json" />,
}));

describe('RootLayout CSP nonce', () => {
    it('passes the request nonce header into Providers', async () => {
        headersMock.mockResolvedValue(new Headers({ 'x-nonce': 'layout-nonce' }));

        const { default: RootLayout } = await import('@/app/layout');
        const markup = renderToStaticMarkup(await RootLayout({ children: <main>Page</main> }));

        expect(markup).toContain('data-provider-nonce="layout-nonce"');
    });
});
