'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from 'next-themes';
import { AuthProvider } from './auth-context';
import { TenantProvider } from './tenant-context';
import { useState } from 'react';

import { Toaster } from '@/components/ui/toaster';
import { CSPostHogProvider } from './posthog-provider';

export function Providers({ children }: { children: React.ReactNode }) {
    const [queryClient] = useState(() => new QueryClient({
        defaultOptions: {
            queries: {
                staleTime: 60 * 1000,
                retry: 1,
            },
        },
    }));

    return (
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
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
