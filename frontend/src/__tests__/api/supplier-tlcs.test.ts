import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '@/lib/api-client';

type GetFn = (url: string, config?: unknown) => Promise<{ data: unknown }>;
const adminClient = (apiClient as unknown as { adminClient: { get: GetFn } }).adminClient;

afterEach(() => {
    vi.restoreAllMocks();
});

const lot = { id: 't1', facility_id: 'f1', tlc_code: 'L1', status: 'active', event_count: 0, created_at: '2026-10-01T00:00:00Z' };

describe('listSupplierTLCs', () => {
    it('unwraps the paginated envelope and uses total as the count (SEL-415 NaN root cause)', async () => {
        vi.spyOn(adminClient, 'get').mockResolvedValue({ data: { items: [lot], total: 120, skip: 0, limit: 50 } });
        const result = await apiClient.listSupplierTLCs('f1');
        expect(result).toEqual({ items: [lot], total: 120 });
    });

    it('accepts a bare array', async () => {
        vi.spyOn(adminClient, 'get').mockResolvedValue({ data: [lot] });
        expect(await apiClient.listSupplierTLCs('f1')).toEqual({ items: [lot], total: 1 });
    });

    it('defaults missing items/total to an empty list and 0', async () => {
        vi.spyOn(adminClient, 'get').mockResolvedValue({ data: {} });
        expect(await apiClient.listSupplierTLCs('f1')).toEqual({ items: [], total: 0 });
        vi.spyOn(adminClient, 'get').mockResolvedValue({ data: null });
        expect(await apiClient.listSupplierTLCs('f1')).toEqual({ items: [], total: 0 });
    });
});
