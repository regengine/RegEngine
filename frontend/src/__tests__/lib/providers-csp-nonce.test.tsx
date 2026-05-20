import { render, screen } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Providers } from '@/lib/providers';

const themeProviderProps = vi.hoisted((): Array<Record<string, unknown>> => []);

vi.mock('next-themes', () => ({
    ThemeProvider: ({ children, nonce, ...props }: PropsWithChildren<Record<string, unknown>>) => {
        themeProviderProps.push({ nonce, ...props });

        return (
            <div data-testid="theme-provider" data-nonce={String(nonce ?? '')}>
                {children}
            </div>
        );
    },
}));

vi.mock('@/lib/posthog-provider', () => ({
    CSPostHogProvider: ({ children }: PropsWithChildren) => <>{children}</>,
}));

vi.mock('@/lib/auth-context', () => ({
    AuthProvider: ({ children }: PropsWithChildren) => <>{children}</>,
}));

vi.mock('@/lib/tenant-context', () => ({
    TenantProvider: ({ children }: PropsWithChildren) => <>{children}</>,
}));

vi.mock('@/components/ui/toaster', () => ({
    Toaster: () => <div data-testid="toaster" />,
}));

describe('Providers CSP nonce', () => {
    it('passes the middleware nonce to next-themes bootstrap script', () => {
        themeProviderProps.length = 0;

        render(
            <Providers nonce="provider-nonce">
                <div>App content</div>
            </Providers>,
        );

        expect(screen.getByTestId('theme-provider')).toHaveAttribute('data-nonce', 'provider-nonce');
        expect(themeProviderProps[0]).toMatchObject({
            nonce: 'provider-nonce',
            attribute: 'class',
            defaultTheme: 'light',
            enableSystem: false,
            storageKey: 're-theme-v2',
        });
    });
});
