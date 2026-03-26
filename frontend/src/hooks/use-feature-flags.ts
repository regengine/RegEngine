'use client';

import { useState, useEffect, useCallback } from 'react';
import { getServiceURL } from '@/lib/api-config';
import { useAuth } from '@/lib/auth-context';

interface FeatureFlags {
    enabled: string[];
    disabled: string[];
}

const CACHE_KEY = 'regengine_feature_flags';
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

interface CachedFlags {
    flags: FeatureFlags;
    timestamp: number;
}

/**
 * Hook to check which backend routers are enabled/disabled.
 *
 * Calls GET /api/v1/features (ingestion service) and caches the result.
 * Use `isEnabled('router_name')` to check before rendering features
 * that depend on optional backend routers (H10 from API audit).
 */
export function useFeatureFlags() {
    const { apiKey } = useAuth();
    const [flags, setFlags] = useState<FeatureFlags | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        // Try cache first
        try {
            const cached = localStorage.getItem(CACHE_KEY);
            if (cached) {
                const parsed: CachedFlags = JSON.parse(cached);
                if (Date.now() - parsed.timestamp < CACHE_TTL) {
                    setFlags(parsed.flags);
                    setLoading(false);
                    return;
                }
            }
        } catch {
            // Cache miss or corrupt — fetch fresh
        }

        const base = getServiceURL('ingestion');
        fetch(`${base}/api/v1/features`, {
            headers: {
                'Content-Type': 'application/json',
                'X-RegEngine-API-Key': apiKey || '',
            },
        })
            .then(res => {
                if (!res.ok) throw new Error(`${res.status}`);
                return res.json();
            })
            .then((data: FeatureFlags) => {
                setFlags(data);
                try {
                    localStorage.setItem(CACHE_KEY, JSON.stringify({
                        flags: data,
                        timestamp: Date.now(),
                    }));
                } catch {
                    // localStorage full — ignore
                }
            })
            .catch(err => {
                setError(err instanceof Error ? err.message : 'Failed to load features');
                // Assume all enabled if we can't reach the endpoint
                setFlags({ enabled: [], disabled: [] });
            })
            .finally(() => setLoading(false));
    }, [apiKey]);

    const isEnabled = useCallback(
        (routerName: string): boolean => {
            if (!flags) return true; // Assume enabled while loading
            // If disabled list is empty and enabled list is empty, assume all enabled
            if (flags.disabled.length === 0) return true;
            return !flags.disabled.includes(routerName.toLowerCase());
        },
        [flags],
    );

    const isDisabled = useCallback(
        (routerName: string): boolean => !isEnabled(routerName),
        [isEnabled],
    );

    return {
        flags,
        loading,
        error,
        isEnabled,
        isDisabled,
    };
}
