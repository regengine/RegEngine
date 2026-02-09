'use client';

import React, { createContext, useContext, useState, useEffect } from 'react';
import { apiClient } from './api-client';

// Default to System Tenant if no other context is available
const DEFAULT_TENANT_ID = '00000000-0000-0000-0000-000000000001';

interface TenantContextType {
    tenantId: string;
    setTenantId: (id: string) => void;
    isSystemTenant: boolean;
}

const TenantContext = createContext<TenantContextType | undefined>(undefined);

export function TenantProvider({ children }: { children: React.ReactNode }) {
    const [tenantId, setTenantId] = useState<string>(DEFAULT_TENANT_ID);

    // Load from local storage on mount
    useEffect(() => {
        const stored = localStorage.getItem('regengine_tenant_id');
        if (stored) {
            setTenantId(stored);
            // Sync with API client
            apiClient.setCurrentTenant(stored);
        } else {
            // Set default tenant in API client
            apiClient.setCurrentTenant(DEFAULT_TENANT_ID);
        }
    }, []);

    // Update local storage and API client on change
    const updateTenant = (id: string) => {
        setTenantId(id);
        localStorage.setItem('regengine_tenant_id', id);
        // Sync with API client for X-Tenant-ID header
        apiClient.setCurrentTenant(id);
    };

    const value = {
        tenantId,
        setTenantId: updateTenant,
        isSystemTenant: tenantId === DEFAULT_TENANT_ID,
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

