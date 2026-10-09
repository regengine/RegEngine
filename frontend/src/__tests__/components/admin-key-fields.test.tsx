import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminPage from '@/app/admin/page';

const mockUseAuth = vi.hoisted(() => vi.fn());
const mockUseAPIKeys = vi.hoisted(() => vi.fn());
const mockCreateKey = vi.hoisted(() => vi.fn());
const mockGenerateKey = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/hooks/use-api', () => ({
    useAPIKeys: (enabled: boolean) => mockUseAPIKeys(enabled),
    useCreateAPIKey: () => ({ mutateAsync: mockCreateKey, isPending: false }),
    useGenerateAPIKey: () => ({ mutateAsync: mockGenerateKey, isPending: false }),
    useRevokeAPIKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

function sysadminAuth() {
    mockUseAuth.mockReturnValue({
        isAuthenticated: true,
        isHighAssuranceSession: true,
        user: { is_sysadmin: true },
        setApiKey: vi.fn(),
        tenantId: 'tenant-1',
    });
}

describe('AdminPage key field names', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        sysadminAuth();
        mockUseAPIKeys.mockReturnValue({
            data: [],
            isLoading: false,
            refetch: vi.fn(),
            error: null,
        });
    });

    it('shows a created key returned under the `key` field name', async () => {
        mockCreateKey.mockResolvedValue({
            id: 'key-1',
            key_id: 'key-1',
            key: 'rge_test_created_key_abc', // pragma: allowlist secret
            name: 'New API Key',
            created_at: '2026-01-01T00:00:00.000Z',
        });

        render(<AdminPage />);
        await userEvent.click(screen.getByRole('button', { name: 'New Key' }));
        await userEvent.click(screen.getByRole('button', { name: 'Create Key' }));

        await waitFor(() =>
            expect(screen.getByText('API Key Created Successfully')).toBeInTheDocument(),
        );
        expect(screen.getByText('rge_test_created_key_abc')).toBeInTheDocument(); // pragma: allowlist secret
    });

    it('shows a generated key returned under the `key` field name', async () => {
        mockGenerateKey.mockResolvedValue({
            id: 'key-2',
            key_id: 'key-2',
            key: 'rge_test_generated_key_abc', // pragma: allowlist secret
            name: 'Developer Portal Generated Key',
            created_at: '2026-01-01T00:00:00.000Z',
        });

        render(<AdminPage />);
        await userEvent.click(screen.getByRole('button', { name: 'Generate New API Key' }));

        await waitFor(() => expect(screen.getByText('API Key generated')).toBeInTheDocument());
        expect(screen.getByText('rge_test_generated_key_abc')).toBeInTheDocument(); // pragma: allowlist secret
    });

    it('lists and revokes keys identified by `id` instead of `key_id`', async () => {
        mockUseAPIKeys.mockReturnValue({
            data: [
                {
                    id: 'key-abc-1',
                    name: 'Ops key',
                    created_at: '2026-01-01T00:00:00.000Z',
                },
            ],
            isLoading: false,
            refetch: vi.fn(),
            error: null,
        });

        render(<AdminPage />);

        expect(screen.getByText('key-abc-1')).toBeInTheDocument();
        await userEvent.click(screen.getByRole('button', { name: 'Revoke API key' }));
        expect(await screen.findByText('Revoke this API key?')).toBeInTheDocument();
    });
});
