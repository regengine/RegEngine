import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ComplianceStatusPage from '@/app/compliance/status/page';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseTenantContext = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenantContext: () => mockUseTenantContext(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: (service: string) => service === 'admin' ? '/api/admin' : `/api/${service}`,
}));

vi.mock('@/components/dashboard/compliance-status-widget', () => ({
    ComplianceStatusWidget: ({ onAlertClick }: { onAlertClick?: (alert: any) => void }) => (
        <button
            type="button"
            onClick={() => onAlertClick?.({
                id: 'alert-1',
                title: 'Recall alert',
                severity: 'HIGH',
                severity_emoji: '!',
                countdown_display: '23h',
                countdown_seconds: 82800,
                is_expired: false,
                status: 'ACTIVE',
                required_actions: [],
                created_at: '2026-05-07T00:00:00.000Z',
            })}
        >
            Open alert
        </button>
    ),
}));

vi.mock('@/components/dashboard/alert-detail-dialog', () => ({
    AlertDetailDialog: ({ open, onAcknowledge, onResolve }: any) => open ? (
        <div>
            <button type="button" onClick={() => onAcknowledge('alert-1')}>Acknowledge</button>
            <button type="button" onClick={() => onResolve('alert-1', 'resolved via dialog')}>Resolve</button>
        </div>
    ) : null,
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
        AlertCircle: Stub,
        Clock: Stub,
        Shield: Stub,
        Settings: Stub,
    };
});

describe('ComplianceStatusPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.spyOn(console, 'error').mockImplementation(() => {});
        mockUseTenantContext.mockReturnValue({
            selectedTenant: { id: 'tenant-123' },
        });
        mockUseAuth.mockReturnValue({
            user: { id: 'user-1', email: 'owner@example.com' },
        });
        fetchWithCsrfMock.mockResolvedValue({
            ok: false,
            json: async () => ({}),
        });
    });

    it('acknowledges alerts through the admin proxy without browser auth headers', async () => {
        const user = userEvent.setup();
        render(<ComplianceStatusPage />);

        await user.click(screen.getByRole('button', { name: 'Open alert' }));
        await user.click(screen.getByRole('button', { name: 'Acknowledge' }));

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalled();
        });

        const [url, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        const headers = new Headers(init.headers);

        expect(url).toBe('/api/admin/v1/compliance/alerts/tenant-123/alert-1/acknowledge');
        expect(init.method).toBe('POST');
        expect(init.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(JSON.parse(String(init.body))).toEqual({});
    });

    it('resolves alerts through the admin proxy without browser auth headers or client-supplied user ids', async () => {
        const user = userEvent.setup();
        render(<ComplianceStatusPage />);

        await user.click(screen.getByRole('button', { name: 'Open alert' }));
        await user.click(screen.getByRole('button', { name: 'Resolve' }));

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalled();
        });

        const [url, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        const headers = new Headers(init.headers);

        expect(url).toBe('/api/admin/v1/compliance/alerts/tenant-123/alert-1/resolve');
        expect(init.method).toBe('POST');
        expect(init.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(JSON.parse(String(init.body))).toEqual({ notes: 'resolved via dialog' });
        expect(String(init.body)).not.toContain('user_id');
    });
});
