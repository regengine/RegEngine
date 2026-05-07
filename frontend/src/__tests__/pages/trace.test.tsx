import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TracePage from '@/app/trace/page';

const mockUseAuth = vi.hoisted(() => vi.fn());
const getSupplierFDAExportPreviewMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api-client', () => ({
    apiClient: {
        getSupplierFDAExportPreview: (...args: any[]) => getSupplierFDAExportPreviewMock(...args),
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

vi.mock('@/components/ui/input', () => ({
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
    };
});

describe('TracePage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
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

    it('keeps trace actions disabled when no tenant session is available', async () => {
        mockUseAuth.mockReturnValue({
            hasTenantSession: false,
        });

        const user = userEvent.setup();
        render(<TracePage />);

        const button = screen.getByRole('button', { name: 'Trace' });
        await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-2026-SAL-0001');

        expect(button).toBeDisabled();
        expect(getSupplierFDAExportPreviewMock).not.toHaveBeenCalled();
    });
});
