'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from 'next-themes';
import { AuthProvider } from './auth-context';
import { TenantProvider } from './tenant-context';
import { useCallback, useState } from 'react';

import { Toaster } from '@/components/ui/toaster';
import { CSPostHogProvider } from './posthog-provider';

type ProvidersProps = {
    children: React.ReactNode;
    nonce?: string;
};

export function Providers({ children, nonce }: ProvidersProps) {
    const [queryClient] = useState(() => new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 60 * 1000,
                retry: 1,
            },
        },
    }));

    const resetSessionCache = useCallback(() => {
        // Cancel before removal so late results cannot populate the next identity.
        void queryClient.cancelQueries();
        queryClient.clear();
    }, [queryClient]);

    return (
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} storageKey="re-theme-v2" nonce={nonce}>
            <CSPostHogProvider>
                <QueryClientProvider client={queryClient}>
                    <AuthProvider resetSessionCache={resetSessionCache}>
                        <TenantProvider resetSessionCache={resetSessionCache}>
                            {children}
                            <Toaster />
                        </TenantProvider>
                    </AuthProvider>
                </QueryClientProvider>
            </CSPostHogProvider>
        </ThemeProvider>
    );
}
