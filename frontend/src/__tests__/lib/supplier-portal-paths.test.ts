import { describe, expect, it } from 'vitest';

import { isCsrfExempt } from '@/lib/csrf';
import {
    INGESTION_PROXY_PREFIX,
    SUPPLIER_PORTAL_MUTATION_PATTERN,
    isPublicSupplierPortalPath,
} from '@/lib/supplier-portal-paths';

const TOKEN = 'test-portal-link-token';
const proxyRelative = (browserPath: string) => browserPath.slice(INGESTION_PROXY_PREFIX.length);

describe('supplier portal path rules', () => {
    it('treats portal details, preflight and submit as public, and link management as not', () => {
        expect(isPublicSupplierPortalPath(`api/v1/portal/${TOKEN}`)).toBe(true);
        expect(isPublicSupplierPortalPath(`api/v1/portal/${TOKEN}/preflight`)).toBe(true);
        expect(isPublicSupplierPortalPath(`api/v1/portal/${TOKEN}/submit`)).toBe(true);
        expect(isPublicSupplierPortalPath('api/v1/portal/links')).toBe(false);
        expect(isPublicSupplierPortalPath(`api/v1/portal/links/${TOKEN}/revoke`)).toBe(false);
        expect(isPublicSupplierPortalPath(`api/v1/portal/${TOKEN}/submit/extra`)).toBe(false);
        expect(isPublicSupplierPortalPath(`api/v1/ingest/csv`)).toBe(false);
    });

    it('never exempts from CSRF a path the proxy does not treat as public', () => {
        // Every path the CSRF rule can match must also be public at the proxy.
        const candidates = [
            `/api/ingestion/api/v1/portal/${TOKEN}/preflight`,
            `/api/ingestion/api/v1/portal/${TOKEN}/submit`,
            `/api/ingestion/api/v1/portal/${'a'.repeat(16)}/submit`,
            `/api/ingestion/api/v1/portal/${'Z'.repeat(128)}/preflight`,
            '/api/ingestion/api/v1/portal/links/submit',
            `/api/ingestion/api/v1/portal/links/${TOKEN}/revoke`,
            `/api/ingestion/api/v1/portal/${TOKEN}`,
            `/api/ingestion/api/v1/portal/${TOKEN}/submit/extra`,
            '/api/ingestion/api/v1/ingest/csv',
        ];
        const pattern = new RegExp(SUPPLIER_PORTAL_MUTATION_PATTERN);
        let exempted = 0;
        for (const path of candidates) {
            if (!pattern.test(path)) continue;
            exempted += 1;
            expect(path.startsWith(INGESTION_PROXY_PREFIX), path).toBe(true);
            expect(isPublicSupplierPortalPath(proxyRelative(path)), path).toBe(true);
            expect(isCsrfExempt(path, 'POST'), path).toBe(true);
        }
        expect(exempted).toBe(4);
    });

    it('keeps the CSRF pattern anchored to the proxy prefix and to POST-only steps', () => {
        expect(SUPPLIER_PORTAL_MUTATION_PATTERN.startsWith(`^${INGESTION_PROXY_PREFIX}api/v1/portal/`)).toBe(true);
        expect(SUPPLIER_PORTAL_MUTATION_PATTERN.endsWith('/(?:preflight|submit)$')).toBe(true);
    });
});
