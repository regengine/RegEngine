/**
 * Integrations page: profile LOAD failures and profile SAVE failures are
 * separate errors. The load-error Retry only appears for load failures and
 * reloads the list; a save failure shows its own message with a "Retry save"
 * that re-attempts the create — never the load Retry.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DashboardIntegrationsPage from '@/app/dashboard/integrations/page';
import type { IntegrationProfile } from '@/types/api';

const mocks = vi.hoisted(() => ({
    tenantId: 'test-tenant',
    isAuthenticated: true,
    listIntegrationProfiles: vi.fn(),
    createIntegrationProfile: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ isAuthenticated: mocks.isAuthenticated }),
}));
vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => ({ tenantId: mocks.tenantId }),
}));
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        listIntegrationProfiles: mocks.listIntegrationProfiles,
        createIntegrationProfile: mocks.createIntegrationProfile,
    },
}));

function makeProfile(overrides: Partial<IntegrationProfile> = {}): IntegrationProfile {
    return {
        profile_id: crypto.randomUUID(),
        tenant_id: mocks.tenantId,
        display_name: 'FreshPack shipping CSV',
        source_type: 'csv',
        field_mapping: { cte_type: 'event_type' },
        default_cte_type: 'shipping',
        status: 'active',
        confidence: 0.82,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        ...overrides,
    };
}

describe('integrations page profile errors', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mocks.tenantId = crypto.randomUUID();
        mocks.isAuthenticated = true;
    });

    it('load failure shows the load Retry, which reloads the list', async () => {
        mocks.listIntegrationProfiles
            .mockRejectedValueOnce(new Error('backend down'))
            .mockResolvedValueOnce({ profiles: [], total: 0 });

        render(<DashboardIntegrationsPage />);

        expect(
            await screen.findByText('Unable to load saved integration profiles for this workspace.'),
        ).toBeInTheDocument();
        const retry = screen.getByRole('button', { name: 'Retry' });
        expect(retry).toBeInTheDocument();

        await userEvent.click(retry);

        await waitFor(() => expect(mocks.listIntegrationProfiles).toHaveBeenCalledTimes(2));
        await waitFor(() =>
            expect(
                screen.queryByText('Unable to load saved integration profiles for this workspace.'),
            ).not.toBeInTheDocument(),
        );
        expect(screen.getByText('No profiles yet.')).toBeInTheDocument();
    });

    it('save failure shows its own message with a save retry, not the load Retry', async () => {
        mocks.listIntegrationProfiles.mockResolvedValue({ profiles: [], total: 0 });
        mocks.createIntegrationProfile.mockRejectedValueOnce(new Error('save failed'));

        render(<DashboardIntegrationsPage />);

        expect(await screen.findByText('No profiles yet.')).toBeInTheDocument();

        fireEvent.change(screen.getByPlaceholderText('FreshPack shipping CSV'), {
            target: { value: 'FreshPack shipping CSV' },
        });
        await userEvent.click(screen.getByRole('button', { name: 'Save profile' }));

        expect(
            await screen.findByText(
                'Unable to save the integration profile. Check workspace access and try again.',
            ),
        ).toBeInTheDocument();
        // The load-error Retry must not appear for a save failure.
        expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
        expect(screen.queryByText('Unable to load saved integration profiles')).not.toBeInTheDocument();

        // "Retry save" re-attempts the create; success clears the error.
        mocks.createIntegrationProfile.mockResolvedValueOnce(makeProfile());
        await userEvent.click(screen.getByRole('button', { name: 'Retry save' }));

        await waitFor(() => expect(mocks.createIntegrationProfile).toHaveBeenCalledTimes(2));
        await waitFor(() =>
            expect(
                screen.queryByText(
                    'Unable to save the integration profile. Check workspace access and try again.',
                ),
            ).not.toBeInTheDocument(),
        );
        await screen.findByText('FreshPack shipping CSV', { selector: 'div' });
    });
});
