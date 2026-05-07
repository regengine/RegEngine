import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ReceivingDockPage from '@/app/dashboard/receiving/page';

const mockUseAuth = vi.fn();
vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

const mockToast = vi.fn();
vi.mock('@/components/ui/use-toast', () => ({
    useToast: () => ({ toast: mockToast }),
}));

const mockParseGS1 = vi.fn();
vi.mock('@/lib/gs1-parser', () => ({
    parseGS1: (value: string) => mockParseGS1(value),
}));

const mockNotifyDashboardRefresh = vi.fn();
vi.mock('@/hooks/use-dashboard-refresh', () => ({
    notifyDashboardRefresh: () => mockNotifyDashboardRefresh(),
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

describe('ReceivingDockPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            tenantId: 'tenant-123',
        });
        mockParseGS1.mockImplementation((raw: string) => ({
            raw,
            gtin: '',
            tlc: '',
        }));
        global.fetch = vi.fn() as any;
    });

    it('looks up GTINs through the cookie-backed proxy without browser auth headers', async () => {
        (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
            ok: true,
            json: async () => ({
                found: true,
                product: {
                    name: 'Romaine Hearts',
                },
            }),
        });

        render(<ReceivingDockPage />);

        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.click(screen.getByRole('button', { name: /add item/i }));
        fireEvent.change(screen.getByPlaceholderText('Barcode / GTIN'), {
            target: { value: '01234567' },
        });

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalled();
        });

        const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string, RequestInit | undefined][];
        const [url, init] = calls[0]!;
        const headers = new Headers(init?.headers);

        expect(url).toBe('/api/ingestion/api/v1/products/tenant-123/lookup?gtin=01234567');
        expect(init?.credentials).toBe('include');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(headers.get('X-Tenant-ID')).toBeNull();
        expect(screen.getByDisplayValue('Romaine Hearts')).toBeInTheDocument();
    });

    it('posts receiving ingests through the cookie-backed proxy without browser auth headers', async () => {
        mockParseGS1.mockReturnValue({
            raw: 'scan-1',
            gtin: '00614141000012',
            tlc: 'TLC-ROM-20260426-001',
        });
        (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
            ok: true,
            json: async () => ({ accepted: 1 }),
        });

        render(<ReceivingDockPage />);

        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.change(screen.getByPlaceholderText('Scan or type barcode...'), {
            target: { value: 'scan-1' },
        });
        fireEvent.click(screen.getByRole('button', { name: /^scan$/i }));

        await waitFor(() => {
            expect(screen.getByRole('button', { name: /confirm & ingest all \(1 items\)/i })).toBeEnabled();
        });

        fireEvent.click(screen.getByRole('button', { name: /confirm & ingest all \(1 items\)/i }));

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalled();
        });

        const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string, RequestInit | undefined][];
        const [url, init] = calls[0]!;
        const headers = new Headers(init?.headers);
        const body = JSON.parse(String(init?.body));

        expect(url).toBe('/api/ingestion/api/v1/webhooks/ingest');
        expect(init?.method).toBe('POST');
        expect(init?.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(headers.get('X-Tenant-ID')).toBeNull();
        expect(body).toMatchObject({
            source: 'receiving_dock',
            tenant_id: 'tenant-123',
        });
        expect(body.events).toHaveLength(1);
        expect(mockNotifyDashboardRefresh).toHaveBeenCalledTimes(1);

        await waitFor(() => {
            expect(screen.getByText('Receiving Complete')).toBeInTheDocument();
        });
    });

    it('does not perform GTIN lookup when the user is signed out', () => {
        mockUseAuth.mockReturnValue({
            isAuthenticated: false,
            tenantId: 'tenant-123',
        });

        render(<ReceivingDockPage />);

        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.click(screen.getByRole('button', { name: /add item/i }));
        fireEvent.change(screen.getByPlaceholderText('Barcode / GTIN'), {
            target: { value: '01234567' },
        });

        expect(global.fetch).not.toHaveBeenCalled();
    });
});
