import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: fetchWithCsrfMock,
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: (service: string) => (service === 'ingestion' ? '/api/ingestion' : `/api/${service}`),
}));

function authFailure(status: number) {
    return {
        ok: false,
        status,
        statusText: status === 401 ? 'Unauthorized' : 'Forbidden',
        json: async () => ({ detail: 'nope' }),
    };
}

describe('apiFetch adversarial: auth failures must not retry and must keep status', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('sends exactly one request on 401 (no retry of auth failures)', async () => {
        fetchWithCsrfMock.mockResolvedValue(authFailure(401));
        const { fetchAlerts } = await import('@/lib/api-hooks');
        await expect(fetchAlerts('tenant-123')).rejects.toThrow();
        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1);
    });

    it('sends exactly one request on 403 (no retry of forbidden)', async () => {
        fetchWithCsrfMock.mockResolvedValue(authFailure(403));
        const { fetchComplianceScore } = await import('@/lib/api-hooks');
        await expect(fetchComplianceScore('tenant-123')).rejects.toThrow();
        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1);
    });

    it('keeps the 401 status machine-readable for login redirects', async () => {
        fetchWithCsrfMock.mockResolvedValue(authFailure(401));
        const { fetchAlerts } = await import('@/lib/api-hooks');
        const err = await fetchAlerts('tenant-123').catch((e: unknown) => e) as {
            status?: number; response?: { status?: number }; message?: string;
        };
        expect(err.message).toContain('401');
        expect(err.status ?? err.response?.status).toBe(401);
    });

    it('keeps the 403 status machine-readable for forbidden UI', async () => {
        fetchWithCsrfMock.mockResolvedValue(authFailure(403));
        const { fetchComplianceScore } = await import('@/lib/api-hooks');
        const err = await fetchComplianceScore('tenant-123').catch((e: unknown) => e) as {
            status?: number; response?: { status?: number }; message?: string;
        };
        expect(err.message).toContain('403');
        expect(err.status ?? err.response?.status).toBe(403);
    });

    it('does not re-execute a POST when the success body is malformed', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            status: 200,
            statusText: 'OK',
            json: async () => { throw new SyntaxError('Unexpected end of JSON input'); },
        });
        const { acknowledgeAlert } = await import('@/lib/api-hooks');
        await expect(
            acknowledgeAlert('tenant-123', null, 'alert-1'),
        ).rejects.toThrow();
        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1);
    });

    it('still retries 429 and 5xx before giving up', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: false, status: 503, statusText: 'Service Unavailable', json: async () => ({}),
        });
        const { fetchAlerts } = await import('@/lib/api-hooks');
        await expect(fetchAlerts('tenant-123')).rejects.toThrow(/503/);
        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(3);
    });
});
