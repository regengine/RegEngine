import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TracePage from '@/app/trace/page';

const mockUseAuth = vi.hoisted(() => vi.fn());
const getSupplierFDAExportPreviewMock = vi.hoisted(() => vi.fn());
const downloadSupplierFDARecordsMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

// The global setup mock returns empty search params; this one lets a case
// arrive the way a scanned label QR does, with ?tlc= set.
const mockSearchParams = vi.hoisted(() => ({ query: '' }));
vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
    usePathname: () => '/trace',
    useSearchParams: () => new URLSearchParams(mockSearchParams.query),
}));

vi.mock('@/lib/api-client', () => ({
    apiClient: {
        getSupplierFDAExportPreview: (...args: any[]) => getSupplierFDAExportPreviewMock(...args),
        downloadSupplierFDARecords: (...args: any[]) => downloadSupplierFDARecordsMock(...args),
    },
}));

vi.mock('@/components/layout/page-container', () => ({
    PageContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/ui/card', () => ({
    Card: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardContent: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardHeader: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardTitle: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardDescription: ({ children, ...props }: any) => <div {...props}>{children}</div>,
}));

vi.mock('@/components/ui/button', () => ({
    Button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
}));

vi.mock('@/components/ui/badge', () => ({
    Badge: ({ children, ...props }: any) => <span {...props}>{children}</span>,
}));

// Spread the real module: these suites only need to replace <Input> itself, and
// a hand-written factory silently breaks any page importing another export
// (fieldControlClasses, the shared control recipe) the moment one is added.
vi.mock('@/components/ui/input', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/components/ui/input')>()),
    Input: (props: any) => <input {...props} />,
}));

vi.mock('@/components/ui/spinner', () => ({
    Spinner: () => <div>Loading...</div>,
}));

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    },
}));

vi.mock('lucide-react', () => {
    const Stub = (props: any) => <svg {...props} />;
    return {
        Search: Stub,
        ArrowRight: Stub,
        MapPin: Stub,
        Calendar: Stub,
        Package: Stub,
        AlertTriangle: Stub,
        Download: Stub,
    };
});

describe('TracePage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockSearchParams.query = '';
        getSupplierFDAExportPreviewMock.mockResolvedValue({
            total_count: 1,
            rows: [
                {
                    event_id: 'evt-1',
                    cte_type: 'shipping',
                    event_time: '2026-05-07T00:00:00.000Z',
                    facility_name: 'Acme Cold Storage',
                    quantity: '10',
                    unit_of_measure: 'cases',
                    payload_sha256: 'abc123',
                    product_description: 'Spinach',
                },
            ],
        });
    });

    it('runs trace queries for tenant sessions without relying on apiKey truthiness', async () => {
        mockUseAuth.mockReturnValue({
            hasTenantSession: true,
        });

        const user = userEvent.setup();
        render(<TracePage />);

        await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-2026-SAL-0001');
        await user.click(screen.getByRole('button', { name: 'Trace' }));

        await waitFor(() => {
            expect(getSupplierFDAExportPreviewMock).toHaveBeenCalledWith(
                undefined,
                500,
                'TLC-2026-SAL-0001',
            );
        });
    });

    it('prefills the lot from ?tlc= so a scanned label QR lands ready to trace', () => {
        mockUseAuth.mockReturnValue({ hasTenantSession: true });
        mockSearchParams.query = 'tlc=LOT-2024%2F001';

        render(<TracePage />);

        expect(screen.getByPlaceholderText(/enter tlc/i)).toHaveValue('LOT-2024/001');
        expect(screen.getByRole('button', { name: 'Trace' })).toBeEnabled();
    });

    it('keeps trace actions disabled when no tenant session is available', async () => {
        mockUseAuth.mockReturnValue({
            hasTenantSession: false,
        });

        const user = userEvent.setup();
        render(<TracePage />);

        const button = screen.getByRole('button', { name: 'Trace' });
        await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-2026-SAL-0001');

        expect(button).toBeDisabled();
        expect(screen.getByRole('button', { name: /export fda spreadsheet/i })).toBeDisabled();
        expect(getSupplierFDAExportPreviewMock).not.toHaveBeenCalled();
        expect(downloadSupplierFDARecordsMock).not.toHaveBeenCalled();
    });

    it('exports the FDA sortable spreadsheet for the entered lot on demand', async () => {
        mockUseAuth.mockReturnValue({ hasTenantSession: true });
        downloadSupplierFDARecordsMock.mockResolvedValue({
            blob: new Blob(['x']),
            filename: 'fda_traceability_records_20261022T000000Z.xlsx',
            recordCount: 3,
        });
        const createObjectURL = vi.fn(() => 'blob:fda');
        const revokeObjectURL = vi.fn();
        vi.stubGlobal('URL', { ...window.URL, createObjectURL, revokeObjectURL });
        const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

        const user = userEvent.setup();
        render(<TracePage />);

        const exportButton = screen.getByRole('button', { name: /export fda spreadsheet/i });
        expect(exportButton).toBeDisabled();

        await user.type(screen.getByPlaceholderText(/enter tlc/i), ' TLC-2026-SAL-0001 ');
        await user.click(exportButton);

        await waitFor(() => {
            expect(downloadSupplierFDARecordsMock).toHaveBeenCalledWith('xlsx', undefined, 'TLC-2026-SAL-0001');
        });
        expect(clickSpy).toHaveBeenCalled();
        expect(revokeObjectURL).toHaveBeenCalledWith('blob:fda');
        expect(await screen.findByRole('status')).toHaveTextContent(
            'Downloaded fda_traceability_records_20261022T000000Z.xlsx with 3 records for TLC "TLC-2026-SAL-0001".',
        );
        // Export does not run the trace query.
        expect(getSupplierFDAExportPreviewMock).not.toHaveBeenCalled();
        clickSpy.mockRestore();
        vi.unstubAllGlobals();
    });

    it('shows an error when the FDA spreadsheet export fails', async () => {
        mockUseAuth.mockReturnValue({ hasTenantSession: true });
        downloadSupplierFDARecordsMock.mockRejectedValue(new Error('500'));

        const user = userEvent.setup();
        render(<TracePage />);

        await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-2026-SAL-0001');
        await user.click(screen.getByRole('button', { name: /export fda spreadsheet/i }));

        expect(await screen.findByRole('alert')).toHaveTextContent('FDA spreadsheet export failed. Please try again.');
    });
});
