'use client';

import { useEffect, useState } from 'react';

export type OrgType = 'retailer' | 'supplier' | 'manufacturer' | 'distributor' | 'grower' | 'importer';

export interface Organization {
    id: string;
    name: string;
    slug: string;
    plan: string;
    type?: OrgType;
    primary_contact?: string;
    contact_email?: string;
    phone?: string;
    address?: string;
    fei_number?: string;
}

interface UseOrganizationsResult {
    organizations: Organization[];
    isLoading: boolean;
    error: string | null;
}

/**
 * Fetches organizations from fsma.organizations table.
 * Returns empty array (not mock data) when no orgs exist yet.
 */
export function useOrganizations(): UseOrganizationsResult {
    const [organizations, setOrganizations] = useState<Organization[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let cancelled = false;

        async function fetchOrgs() {
            try {
                const response = await fetch('/api/fsma/organizations', { credentials: 'include' });
                const payload = response.ok ? await response.json() : { organizations: [] };

                if (cancelled) return;

                setOrganizations(payload.organizations ?? []);
                setError(typeof payload.error === 'string' ? payload.error : null);
            } catch {
                if (!cancelled) {
                    setOrganizations([]);
                }
            } finally {
                if (!cancelled) setIsLoading(false);
            }
        }

        fetchOrgs();
        return () => { cancelled = true; };
    }, []);

    return { organizations, isLoading, error };
}
