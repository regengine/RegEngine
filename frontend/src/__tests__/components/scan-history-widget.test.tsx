import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { ScanHistoryWidget } from '@/components/dashboard/scan-history-widget';

const mockUseAuth = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => '/api/ingestion',
}));

vi.mock('next/link', () => ({
    default: ({ children, href, ...props }: any) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

vi.mock('lucide-react', () => {
    const Stub = (props: any) => <svg {...props} />;
    return {
        ArrowRight: Stub,
        Package: Stub,
        ScanLine: Stub,
        Truck: Stub,
    };
});

describe('ScanHistoryWidget', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.spyOn(AbortSignal, 'timeout').mockImplementation(() => new AbortController().signal);
        mockUseAuth.mockReturnValue({
            tenantId: 'tenant-123',
            isAuthenticated: true,
        });
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            json: async () => ({ events: [] }),
        }) as any;
    });

    it('loads recent scans through the ingestion proxy without browser auth headers', async () => {
        render(<ScanHistoryWidget />);

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalled();
        });

        const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
        const headers = new Headers(init.headers);

        expect(url).toBe('/api/ingestion/api/v1/webhooks/recent?tenant_id=tenant-123&limit=8');
        expect(init.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(headers.get('X-Tenant-ID')).toBeNull();
    });

    it('does not fetch when the user is signed out', () => {
        mockUseAuth.mockReturnValue({
            tenantId: 'tenant-123',
            isAuthenticated: false,
        });
        global.fetch = vi.fn();

        render(<ScanHistoryWidget />);

        expect(global.fetch).not.toHaveBeenCalled();
    });
});
