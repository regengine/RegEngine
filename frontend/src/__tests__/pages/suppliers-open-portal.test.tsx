/**
 * Supplier portal "open link" button must open backend-supplied URLs with
 * the noopener safeguard so the opened page cannot reach back into the
 * dashboard tab (reverse tabnabbing).
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SupplierDashboardPage, { openPortalUrl } from '@/app/dashboard/suppliers/page';

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => ({ tenantId: 'tenant-1' }),
}));

vi.mock('@/hooks/use-dashboard-refresh', () => ({
    useDashboardRefresh: () => {},
}));

vi.mock('@/lib/experimental-features', () => ({
    experimentalFeaturesEnabled: () => false,
}));

vi.mock('@/lib/api-hooks', () => ({
    fetchWorkbenchReadinessSummary: () => Promise.resolve(null),
}));

const ACTIVE_LINK = {
    portal_id: 'portal-1',
    portal_url: 'https://supplier.example/portal/abc',
    supplier_name: 'Acme Farms',
    tenant_id: 'tenant-1',
    status: 'active',
    created_at: null,
    expires_at: null,
};

vi.mock('@/lib/api-client', () => ({
    apiClient: {
        listPortalLinks: () => Promise.resolve({ links: [ACTIVE_LINK] }),
        listIntegrationProfiles: () => Promise.resolve({ profiles: [] }),
        listSupplierFacilities: () => Promise.resolve([]),
    },
}));

describe('supplier portal open-link safeguard', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('passes noopener/noreferrer when opening a portal URL', () => {
        const openSpy = vi.spyOn(window, 'open').mockReturnValue(null);
        openPortalUrl('https://supplier.example/portal/abc');
        expect(openSpy).toHaveBeenCalledWith(
            'https://supplier.example/portal/abc',
            '_blank',
            'noopener,noreferrer'
        );
    });

    it('clears opener on the opened window', () => {
        const opened = { opener: {} as unknown };
        vi.spyOn(window, 'open').mockReturnValue(opened as unknown as Window);
        openPortalUrl('https://supplier.example/portal/abc');
        expect(opened.opener).toBeNull();
    });

    it('opens the portal link from the dashboard button without window.opener access', async () => {
        const opened = { opener: {} as unknown };
        const openSpy = vi.spyOn(window, 'open').mockReturnValue(opened as unknown as Window);
        render(<SupplierDashboardPage />);
        await userEvent.click(await screen.findByRole('button', { name: 'Open portal' }));
        expect(openSpy).toHaveBeenCalledWith(
            'https://supplier.example/portal/abc',
            '_blank',
            'noopener,noreferrer'
        );
        expect(opened.opener).toBeNull();
    });
});
