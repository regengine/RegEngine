'use client';

import { useEffect, useState } from 'react';
import { createClient } from '@supabase/supabase-js';

// Use a dedicated client that queries the fsma schema.
// Lazy-init to avoid "supabaseUrl is required" errors in test/CI environments.
// SupabaseClient type for non-default schema requires a generic cast.
// Using the base client type since we only call .from().select() on it.
import type { SupabaseClient } from '@supabase/supabase-js';
let _fsmaClient: SupabaseClient | null = null;
function getFsmaClient(): SupabaseClient | null {
    if (!_fsmaClient) {
        const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
        const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
        if (!url || !key) return null;
        // Schema override requires casting — Supabase generics don't support custom schemas without codegen
        _fsmaClient = createClient(url, key, { db: { schema: 'fsma' } } as unknown as Parameters<typeof createClient>[2]);
    }
    return _fsmaClient;
}

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
                const client = getFsmaClient();
                if (!client) {
                    // No Supabase credentials — degrade gracefully (CI/test)
                    setOrganizations([]);
                    setIsLoading(false);
                    return;
                }
                const { data, error: queryError } = await client
                    .from('organizations')
                    .select('id, name, slug, plan, type, primary_contact, contact_email, phone, address, fei_number')
                    .order('name');

                if (cancelled) return;

                if (queryError) {
                    // Table may not exist yet or RLS blocks access — degrade gracefully
                    if (process.env.NODE_ENV !== 'production') {
                        console.warn('Failed to fetch organizations:', queryError.message);
                    }
                    setError(queryError.message);
                    setOrganizations([]);
                } else {
                    setOrganizations(data ?? []);
                }
            } catch (err) {
                if (!cancelled) {
                    if (process.env.NODE_ENV !== 'production') {
                        console.warn('Organizations fetch failed:', err);
                    }
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
