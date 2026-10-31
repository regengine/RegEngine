'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from 'next-themes';
import { usePathname } from 'next/navigation';
import { isForcedDarkRoute } from '@/lib/app-routes';
import { AuthProvider } from './auth-context';
import { TenantProvider } from './tenant-context';
import { useState } from 'react';

import { Toaster } from '@/components/ui/toaster';
import { CSPostHogProvider } from './posthog-provider';

type ProvidersProps = {
    children: React.ReactNode;
    nonce?: string;
};

export function Providers({ children, nonce }: ProvidersProps) {
    const pathname = usePathname();
    const forcedTheme = isForcedDarkRoute(pathname ?? '') ? 'dark' : undefined;
    const [queryClient] = useState(() => new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 60 * 1000,
                retry: 1,
            },
        },
    }));

    return (
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} storageKey="re-theme-v2" nonce={nonce} forcedTheme={forcedTheme}>
            <CSPostHogProvider>
                <QueryClientProvider client={queryClient}>
                    <AuthProvider>
                        <TenantProvider>
                            {children}
                            <Toaster />
                        </TenantProvider>
                    </AuthProvider>
                </QueryClientProvider>
            </CSPostHogProvider>
        </ThemeProvider>
    );
}
