import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ComplianceProfilePage from '@/app/compliance/profile/page';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseTenant = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => mockUseTenant(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: (service: string) => service === 'admin' ? '/api/admin' : `/api/${service}`,
}));

vi.mock('@/components/ui/checkbox', () => ({
    Checkbox: (props: any) => <input type="checkbox" {...props} />,
}));

vi.mock('next/link', () => ({
    default: ({ children, href, ...props }: any) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    },
}));

vi.mock('lucide-react', () => {
    const Stub = (props: any) => <svg {...props} />;
    return {
        Save: Stub,
        Settings: Stub,
        Leaf: Stub,
        MapPin: Stub,
        Building2: Stub,
        Package: Stub,
        ShoppingCart: Stub,
        AlertCircle: Stub,
        CheckCircle: Stub,
        Check: Stub,
    };
});

describe('ComplianceProfilePage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseTenant.mockReturnValue({
            tenantId: 'tenant-123',
        });
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            apiKey: null,
        });
    });

    it('loads the profile through the admin proxy without browser auth headers', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                tenant_id: 'tenant-123',
                product_categories: [],
                supply_regions: [],
                supplier_identifiers: [],
                fda_product_codes: [],
                retailer_relationships: [],
            }),
        });

        render(<ComplianceProfilePage />);

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalled();
        });

        const [url, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        const headers = new Headers(init.headers);

        expect(url).toBe('/api/admin/v1/compliance/profile/tenant-123');
        expect(init.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(headers.get('X-Tenant-ID')).toBeNull();
    });

    it('saves the profile through the admin proxy without browser auth headers', async () => {
        fetchWithCsrfMock
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    tenant_id: 'tenant-123',
                    product_categories: [],
                    supply_regions: [],
                    supplier_identifiers: [],
                    fda_product_codes: [],
                    retailer_relationships: [],
                }),
            })
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({}),
            });

        const user = userEvent.setup();
        render(<ComplianceProfilePage />);

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1);
        });

        await user.click(screen.getByRole('button', { name: 'Save Profile' }));

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledTimes(2);
        });

        const [url, init] = fetchWithCsrfMock.mock.calls[1] as [string, RequestInit];
        const headers = new Headers(init.headers);

        expect(url).toBe('/api/admin/v1/compliance/profile/tenant-123');
        expect(init.method).toBe('PUT');
        expect(init.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(headers.get('X-Tenant-ID')).toBeNull();
    });
});
