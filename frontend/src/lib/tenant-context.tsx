'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiClient } from './api-client';
import { useAuth } from './auth-context';

// Default to System Tenant if no other context is available
export const DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000001';
const TENANT_ID_PATTERN =
    /^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}|[A-Za-z0-9][A-Za-z0-9_-]{0,127})$/;

export function isSafeTenantId(value: unknown): value is string {
    return typeof value === 'string' && TENANT_ID_PATTERN.test(value);
}

interface TenantContextType {
    tenantId: string;
    setTenantId: (id: string) => void;
    isSystemTenant: boolean;
    /**
     * False until the tenant id is trustworthy: either a stored tenant was
     * found at mount, or auth hydration finished. Before that, `tenantId`
     * is the DEFAULT_TENANT_ID placeholder — data hooks that key requests
     * on the tenant should wait for this flag or they fire doomed calls
     * against the placeholder on every cold load.
     */
    isTenantReady: boolean;
}

const TenantContext = createContext<TenantContextType | undefined>(undefined);

function readStoredTenantId(): string | null {
    if (typeof window === 'undefined') {
        return null;
    }

    try {
        const storedTenantId = localStorage.getItem('regengine_tenant_id');
        if (!storedTenantId) {
            return null;
        }
        if (isSafeTenantId(storedTenantId)) {
            return storedTenantId;
        }
        localStorage.removeItem('regengine_tenant_id');
        return null;
    } catch {
        return null;
    }
}

export function TenantProvider({ children }: { children: React.ReactNode }) {
    const { tenantId: authTenantId, isHydrated } = useAuth();
    const [tenantId, setTenantId] = useState<string>(() => readStoredTenantId() || DEFAULT_TENANT_ID);
    const [hadStoredTenant] = useState<boolean>(() => Boolean(readStoredTenantId()));

    // Sync the API client with the tenant this provider already resolved.
    // `tenantId` is lazily initialised from the same readStoredTenantId()
    // call above, so re-setting it here only re-assigned the value state
    // already held; the API-client hand-off is the effect's real work.
    useEffect(() => {
        apiClient.setCurrentTenant(readStoredTenantId() || DEFAULT_TENANT_ID);
    }, []);

    useEffect(() => {
        if (!isHydrated) {
            return;
        }

        const resolvedTenantId = isSafeTenantId(authTenantId) ? authTenantId : readStoredTenantId();
        if (!resolvedTenantId || resolvedTenantId === tenantId) {
            return;
        }

        setTenantId(resolvedTenantId);
        apiClient.setCurrentTenant(resolvedTenantId);
    }, [authTenantId, isHydrated, tenantId]);

    // Update local storage and API client on change
    const updateTenant = (id: string) => {
        const safeTenantId = isSafeTenantId(id) ? id : DEFAULT_TENANT_ID;
        setTenantId(safeTenantId);
        try {
            if (safeTenantId === id) {
                localStorage.setItem('regengine_tenant_id', safeTenantId);
            } else {
                localStorage.removeItem('regengine_tenant_id');
            }
        } catch {
            // Ignore storage write failures; in-memory state still updates.
        }
        // Sync with API client for X-Tenant-ID header
        apiClient.setCurrentTenant(safeTenantId);
    };

    // Ready only once the id is settled: hydration finishing is not enough,
    // because the auth tenant is applied by an effect one render AFTER
    // isHydrated flips — in that gap tenantId is still the placeholder and
    // gated hooks would fire against it anyway.
    const authResolvedTenantId = isHydrated && isSafeTenantId(authTenantId) ? authTenantId : null;
    const awaitingAuthSwap = Boolean(authResolvedTenantId && authResolvedTenantId !== tenantId);

    const value = {
        tenantId,
        setTenantId: updateTenant,
        isSystemTenant: tenantId === DEFAULT_TENANT_ID,
        isTenantReady: (hadStoredTenant || isHydrated) && !awaitingAuthSwap,
    };

    return (
        <TenantContext.Provider value={value}>
            {children}
        </TenantContext.Provider>
    );
}

export function useTenant() {
    const context = useContext(TenantContext);
    if (context === undefined) {
        throw new Error('useTenant must be used within a TenantProvider');
    }
    return context;
}

// Alias for compatibility
export function useTenantContext() {
    const { tenantId, setTenantId, isSystemTenant } = useTenant();
    return {
        selectedTenant: { id: tenantId },
        tenantId,
        setTenantId,
        isSystemTenant,
    };
}
