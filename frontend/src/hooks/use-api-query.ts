'use client';

/**
 * Unified data fetching hooks — the PREFERRED pattern for all new code.
 *
 * Credentials are stored in HTTP-only cookies and injected by the
 * server-side proxy routes (/api/ingestion, /api/admin, etc.).
 * Client code no longer sends API keys in headers.
 */

import {
    useQuery,
    useMutation,
    useQueryClient,
    type UseQueryOptions,
    type UseMutationOptions,
    type QueryKey,
} from '@tanstack/react-query';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { getServiceURL } from '@/lib/api-config';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';

type ServiceName = 'ingestion' | 'admin' | 'compliance' | 'graph';

/**
 * Authenticated fetch helper — used internally by the hooks below.
 * Credentials are in HTTP-only cookies; the proxy injects them server-side.
 */
async function authFetch<T>(
    service: ServiceName,
    path: string,
    options: RequestInit = {},
): Promise<T> {
    const base = getServiceURL(service);
    const res = await fetchWithCsrf(`${base}${path}`, {
        ...options,
        credentials: 'include', // Send cookies to same-origin proxies
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });

    if (!res.ok) {
        throw new Error(`API error: ${res.status} ${res.statusText}`);
    }

    return res.json();
}

/**
 * Authenticated React Query hook for GET requests.
 */
export function useApiQuery<T = unknown>(
    queryKey: QueryKey,
    path: string,
    options?: {
        service?: ServiceName;
        enabled?: boolean;
        refetchInterval?: number | false;
        staleTime?: number;
    } & Omit<UseQueryOptions<T, Error>, 'queryKey' | 'queryFn'>,
) {
    const { apiKey, isAuthenticated } = useAuth();
    const { service = 'ingestion', enabled, ...restOptions } = options ?? {};

    return useQuery<T, Error>({
        queryKey,
        queryFn: () => authFetch<T>(service, path),
        enabled: isAuthenticated && !!apiKey && (enabled ?? true),
        ...restOptions,
    });
}

/**
 * Authenticated React Query hook for mutations (POST/PUT/DELETE).
 */
export function useApiMutate<TData = unknown, TInput = unknown>(
    path: string,
    options?: {
        service?: ServiceName;
        method?: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
        invalidateKeys?: QueryKey[];
    } & Omit<UseMutationOptions<TData, Error, TInput>, 'mutationFn'>,
) {
    const queryClient = useQueryClient();
    const { service = 'ingestion', method = 'POST', invalidateKeys, ...restOptions } = options ?? {};

    return useMutation<TData, Error, TInput>({
        mutationFn: (input: TInput) =>
            authFetch<TData>(service, path, {
                method,
                body: JSON.stringify(input),
            }),
        onSuccess: (...args) => {
            if (invalidateKeys) {
                for (const key of invalidateKeys) {
                    queryClient.invalidateQueries({ queryKey: key });
                }
            }
            restOptions.onSuccess?.(...args);
        },
        ...restOptions,
    });
}

/**
 * Hook that returns the current tenant ID and auth state for manual fetching.
 */
export function useApiContext() {
    const { apiKey, isAuthenticated } = useAuth();
    const { tenantId } = useTenant();

    return {
        apiKey: apiKey || '',
        tenantId,
        isAuthenticated,
        /** Convenience: authenticated fetch for one-off calls */
        fetch: <T>(service: ServiceName, path: string, options?: RequestInit) =>
            authFetch<T>(service, path, options),
    };
}
