'use client';

/**
 * Unified data fetching hooks — the PREFERRED pattern for all new code.
 *
 * Consolidates the 4 existing patterns (M1 from API audit):
 *   1. Direct fetch() with manual headers → use useApiQuery instead
 *   2. apiClient Axios class → use useApiQuery for reads, useApiMutate for writes
 *   3. Raw useQuery() without auth → use useApiQuery (auto-injects credentials)
 *   4. api-hooks.ts standalone functions → pass to useApiQuery's queryFn
 *
 * These wrappers combine React Query with useAuth() so credentials
 * are always sourced from the auth context (never localStorage or env vars).
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

type ServiceName = 'ingestion' | 'admin' | 'compliance' | 'graph';

/**
 * Authenticated fetch helper — used internally by the hooks below.
 * Automatically injects X-RegEngine-API-Key header.
 */
async function authFetch<T>(
    service: ServiceName,
    path: string,
    apiKey: string,
    options: RequestInit = {},
): Promise<T> {
    const base = getServiceURL(service);
    const res = await fetch(`${base}${path}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            'X-RegEngine-API-Key': apiKey,
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
 *
 * Usage:
 *   const { data, isLoading } = useApiQuery(
 *     ['products', tenantId],
 *     `/api/v1/products/${tenantId}`,
 *   );
 *
 * Or with a custom service:
 *   const { data } = useApiQuery(
 *     ['compliance', tenantId],
 *     `/v1/compliance/score/${tenantId}`,
 *     { service: 'compliance' },
 *   );
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
        queryFn: () => authFetch<T>(service, path, apiKey || ''),
        enabled: isAuthenticated && (enabled ?? true),
        ...restOptions,
    });
}

/**
 * Authenticated React Query hook for mutations (POST/PUT/DELETE).
 *
 * Usage:
 *   const { mutateAsync } = useApiMutate<Product, CreateProductInput>(
 *     `/api/v1/products/${tenantId}`,
 *     { method: 'POST', invalidateKeys: [['products', tenantId]] },
 *   );
 *   await mutateAsync({ name: 'Romaine', category: 'Leafy Greens' });
 */
export function useApiMutate<TData = unknown, TInput = unknown>(
    path: string,
    options?: {
        service?: ServiceName;
        method?: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
        invalidateKeys?: QueryKey[];
    } & Omit<UseMutationOptions<TData, Error, TInput>, 'mutationFn'>,
) {
    const { apiKey } = useAuth();
    const queryClient = useQueryClient();
    const { service = 'ingestion', method = 'POST', invalidateKeys, ...restOptions } = options ?? {};

    return useMutation<TData, Error, TInput>({
        mutationFn: (input: TInput) =>
            authFetch<TData>(service, path, apiKey || '', {
                method,
                body: JSON.stringify(input),
            }),
        onSuccess: (...args) => {
            // Auto-invalidate related queries
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
 * Hook that returns the current tenant ID and API key for manual fetching.
 * Use when you need more control than useApiQuery provides.
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
            authFetch<T>(service, path, apiKey || '', options),
    };
}
