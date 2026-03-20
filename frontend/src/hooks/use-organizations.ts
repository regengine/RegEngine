'use client';

import { useEffect, useState } from 'react';
import { createClient } from '@supabase/supabase-js';

// Use a dedicated client that queries the fsma schema
const fsmaClient = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL || '',
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '',
    { db: { schema: 'fsma' } }
);

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
                const { data, error: queryError } = await fsmaClient
                    .from('organizations')
                    .select('id, name, slug, plan, type, primary_contact, contact_email, phone, address, fei_number')
                    .order('name');

                if (cancelled) return;

                if (queryError) {
                    // Table may not exist yet or RLS blocks access — degrade gracefully
                    console.warn('Failed to fetch organizations:', queryError.message);
                    setError(queryError.message);
                    setOrganizations([]);
                } else {
                    setOrganizations(data ?? []);
                }
            } catch (err) {
                if (!cancelled) {
                    console.warn('Organizations fetch failed:', err);
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
