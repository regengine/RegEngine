import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
        fireEvent.click(screen.getByRole('button', { name: /add expected item/i }));
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
            json: async () => ({ accepted: 1, rejected: 0, total: 1, events: [{ traceability_lot_code: 'TLC-ROM-20260426-001', cte_type: 'receiving', status: 'accepted', event_id: 'event-1' }] }),
        });

        render(<ReceivingDockPage />);

        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.change(screen.getByLabelText('Receiving location'), { target: { value: 'Dock A' } });
        fireEvent.change(screen.getByLabelText('TLC source reference'), { target: { value: 'Farm A address' } });
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
        expect(headers.get('Idempotency-Key')).toBeTruthy();
        expect(body.events[0].kdes).toMatchObject({ receive_date: expect.any(String), receiving_location: 'Dock A', immediate_previous_source: 'Valley Fresh Farms', reference_document: 'PO-2026-0042', tlc_source_reference: 'Farm A address' });
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(headers.get('X-Tenant-ID')).toBeNull();
        expect(body).toMatchObject({
            source: 'receiving_dock',
            tenant_id: 'tenant-123',
        });
        expect(body.events).toHaveLength(1);
        expect(mockNotifyDashboardRefresh).toHaveBeenCalledTimes(1);

        await waitFor(() => {
            expect(screen.getByText('Persisted')).toBeInTheDocument();
            expect(screen.queryByText('Receiving Complete')).not.toBeInTheDocument();
        });
    });

    it('does not perform GTIN lookup when the user is signed out', () => {
        mockUseAuth.mockReturnValue({
            isAuthenticated: false,
            tenantId: 'tenant-123',
        });

        render(<ReceivingDockPage />);

        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.click(screen.getByRole('button', { name: /add expected item/i }));
        fireEvent.change(screen.getByPlaceholderText('Barcode / GTIN'), {
            target: { value: '01234567' },
        });

        expect(global.fetch).not.toHaveBeenCalled();
    });
    it('preserves a conflicting observed lot and leaves expected identity pending', async () => {
        mockParseGS1.mockReturnValue({ gtin: '00614141000012', tlc: 'CONFLICT' });
        render(<ReceivingDockPage />);
        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.change(screen.getByPlaceholderText('Scan or type barcode...'), { target: { value: 'conflict' } });
        fireEvent.click(screen.getByRole('button', { name: /^scan$/i }));
        expect(screen.getByDisplayValue('CONFLICT')).toBeInTheDocument();
        expect(screen.queryByText('Identifier matched')).not.toBeInTheDocument();
        expect(screen.getByText('2 pending')).toBeInTheDocument();
    });
    it('retains rejected rows after mixed success and retries only the rejected row', async () => {
        mockParseGS1.mockImplementation((raw: string) => ({ gtin: raw === 'one' ? '00614141000012' : '00614141000029', tlc: raw === 'one' ? 'TLC-ROM-20260426-001' : 'TLC-MIX-20260426-004' }));
        const fetchMock = global.fetch as ReturnType<typeof vi.fn>;
        fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ accepted: 1, rejected: 1, total: 2, events: [
            { traceability_lot_code: 'TLC-ROM-20260426-001', status: 'accepted', event_id: 'event-1' },
            { traceability_lot_code: 'TLC-MIX-20260426-004', status: 'rejected', errors: ['Source invalid'] },
        ] }) }).mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(new Error('offline'));
        render(<ReceivingDockPage />);
        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.change(screen.getByLabelText('Receiving location'), { target: { value: 'Dock A' } });
        fireEvent.change(screen.getByLabelText('TLC source reference'), { target: { value: 'Farm A address' } });
        for (const value of ['one', 'two']) {
            fireEvent.change(screen.getByPlaceholderText('Scan or type barcode...'), { target: { value } });
            fireEvent.click(screen.getByRole('button', { name: /^scan$/i }));
        }
        fireEvent.click(screen.getByRole('button', { name: /confirm & ingest all/i }));
        await screen.findByText('Source invalid');
        expect(screen.queryByText('Receiving Complete')).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: /confirm & ingest all/i }));
        await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
        await waitFor(() => expect(screen.getByRole('button', { name: /confirm & ingest all/i })).toBeEnabled());
        fireEvent.click(screen.getByRole('button', { name: /confirm & ingest all/i }));
        await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
        const retry = fetchMock.mock.calls[1][1];
        expect(JSON.parse(retry.body).events).toHaveLength(1);
        expect(JSON.parse(retry.body).events[0].traceability_lot_code).toBe('TLC-MIX-20260426-004');
        expect(new Headers(retry.headers).get('Idempotency-Key')).toEqual(new Headers(fetchMock.mock.calls[2][1].headers).get('Idempotency-Key'));
        expect(new Headers(retry.headers).get('Idempotency-Key')).not.toEqual(new Headers(fetchMock.mock.calls[0][1].headers).get('Idempotency-Key'));
    });

    it('ignores a delayed catalog lookup after the operator changes the barcode', async () => {
        let resolve!: (value: unknown) => void;
        (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(r => { resolve = r; }));
        render(<ReceivingDockPage />);
        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.click(screen.getByRole('button', { name: /add expected item/i }));
        fireEvent.change(screen.getByPlaceholderText('Barcode / GTIN'), { target: { value: '01234567' } });
        fireEvent.change(screen.getByPlaceholderText('Barcode / GTIN'), { target: { value: 'new' } });
        resolve({ ok: true, json: async () => ({ found: true, product: { name: 'Old product' } }) });
        await waitFor(() => expect(screen.getByPlaceholderText('Product name')).toHaveValue(''));
        expect(screen.queryByDisplayValue('Old product')).not.toBeInTheDocument();
    });

    it.each(['tenant-return', 'auth-reset'])('ignores delayed ingest after %s and preserves a new draft', async (reset) => {
        let resolve!: (value: unknown) => void;
        (global.fetch as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(r => { resolve = r; }));
        mockParseGS1.mockReturnValue({ gtin: '00614141000012', tlc: 'TLC-ROM-20260426-001' });
        const { rerender } = render(<ReceivingDockPage />);
        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.change(screen.getByLabelText('Receiving location'), { target: { value: 'Dock A' } });
        fireEvent.change(screen.getByLabelText('TLC source reference'), { target: { value: 'Farm A address' } });
        fireEvent.change(screen.getByPlaceholderText('Scan or type barcode...'), { target: { value: 'one' } });
        fireEvent.click(screen.getByRole('button', { name: /^scan$/i }));
        fireEvent.click(screen.getByRole('button', { name: /confirm & ingest all/i }));
        mockUseAuth.mockReturnValue({ isAuthenticated: reset !== 'auth-reset', tenantId: reset === 'tenant-return' ? 'tenant-B' : 'tenant-123' });
        rerender(<ReceivingDockPage />);
        mockUseAuth.mockReturnValue({ isAuthenticated: true, tenantId: 'tenant-123' });
        rerender(<ReceivingDockPage />);
        fireEvent.change(screen.getByLabelText('Supplier Name'), { target: { value: 'New supplier' } });
        fireEvent.change(screen.getByLabelText('PO / ASN Number'), { target: { value: 'NEW-PO' } });
        fireEvent.click(screen.getByRole('button', { name: /start receiving$/i }));
        await act(async () => resolve({ ok: true, json: async () => ({ accepted: 1, rejected: 0, total: 1, events: [{ traceability_lot_code: 'TLC-ROM-20260426-001', status: 'accepted', event_id: 'old-event' }] }) }));
        expect(screen.getByText('New supplier')).toBeInTheDocument();
        expect(screen.getByText('NEW-PO')).toBeInTheDocument();
        expect(screen.queryByText('Persisted')).not.toBeInTheDocument();
        expect(mockNotifyDashboardRefresh).not.toHaveBeenCalled();
    });
    it('matches an explicitly known numeric lot instead of a competing numeric GTIN', () => {
        render(<ReceivingDockPage />);
        fireEvent.click(screen.getByRole('button', { name: /load sample po/i }));
        fireEvent.click(screen.getByRole('button', { name: /add expected item/i }));
        fireEvent.change(screen.getByPlaceholderText('Lot Code'), { target: { value: '12345678' } });
        fireEvent.change(screen.getByPlaceholderText('Product name'), { target: { value: 'Numeric lot product' } });
        fireEvent.click(screen.getByRole('button', { name: /add to expected/i }));
        fireEvent.click(screen.getByRole('button', { name: /add expected item/i }));
        fireEvent.change(screen.getByPlaceholderText('Barcode / GTIN'), { target: { value: '12345678' } });
        fireEvent.change(screen.getByPlaceholderText('Lot Code'), { target: { value: 'OTHER' } });
        fireEvent.change(screen.getByPlaceholderText('Product name'), { target: { value: 'Competing barcode product' } });
        fireEvent.click(screen.getByRole('button', { name: /add to expected/i }));
        fireEvent.change(screen.getByPlaceholderText('Scan or type barcode...'), { target: { value: '12345678' } });
        fireEvent.click(screen.getByRole('button', { name: /^scan$/i }));
        expect(screen.getByDisplayValue('12345678')).toBeInTheDocument();
        expect(screen.getByText('Identifier matched')).toBeInTheDocument();
        expect(screen.queryByText(/Unexpected Items/)).not.toBeInTheDocument();
    });

});
