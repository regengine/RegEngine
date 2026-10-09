import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminPage from '@/app/admin/page';
import type { APIKeyResponse } from '@/types/api';

const mockUseAuth = vi.hoisted(() => vi.fn());
const mockUseAPIKeys = vi.hoisted(() => vi.fn());
const mockCreateMutate = vi.hoisted(() => vi.fn());
const mockGenerateMutate = vi.hoisted(() => vi.fn());
const mockRevokeMutate = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/hooks/use-api', () => ({
  useAPIKeys: (enabled: boolean) => mockUseAPIKeys(enabled),
  useCreateAPIKey: () => ({ mutateAsync: mockCreateMutate, isPending: false }),
  useGenerateAPIKey: () => ({ mutateAsync: mockGenerateMutate, isPending: false }),
  useRevokeAPIKey: () => ({ mutateAsync: mockRevokeMutate, isPending: false }),
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

function emptyKeyList() {
  mockUseAPIKeys.mockReturnValue({
    data: [],
    isLoading: false,
    refetch: vi.fn(),
    error: null,
  });
}

const baseKey: APIKeyResponse = {
  id: 'key-1',
  name: 'Test key',
  created_at: '2026-01-01T00:00:00Z',
};

describe('AdminPage alternate key field spellings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sysadminAuth();
  });

  it('shows a created key returned under the `key` spelling', async () => {
    emptyKeyList();
    mockCreateMutate.mockResolvedValue({ ...baseKey, key: 'live-key-spelling-value' });
    const user = userEvent.setup();
    render(<AdminPage />);

    await user.click(screen.getByRole('button', { name: 'New Key' }));
    await user.click(screen.getByRole('button', { name: 'Create Key' }));

    expect(await screen.findByText('API Key Created Successfully')).toBeInTheDocument();
    expect(screen.getByText('live-key-spelling-value')).toBeInTheDocument();
  });

  it('still shows a created key returned under the `api_key` spelling', async () => {
    emptyKeyList();
    mockCreateMutate.mockResolvedValue({ ...baseKey, api_key: 'live-api-key-spelling-value' });
    const user = userEvent.setup();
    render(<AdminPage />);

    await user.click(screen.getByRole('button', { name: 'New Key' }));
    await user.click(screen.getByRole('button', { name: 'Create Key' }));

    expect(await screen.findByText('API Key Created Successfully')).toBeInTheDocument();
    expect(screen.getByText('live-api-key-spelling-value')).toBeInTheDocument();
  });

  it('shows a generated key returned under the `key` spelling', async () => {
    emptyKeyList();
    mockGenerateMutate.mockResolvedValue({ ...baseKey, key: 'live-generated-key-value' });
    const user = userEvent.setup();
    render(<AdminPage />);

    await user.click(screen.getByRole('button', { name: 'Generate New API Key' }));

    expect(await screen.findByText('API Key generated')).toBeInTheDocument();
    expect(screen.getByText('live-generated-key-value')).toBeInTheDocument();
  });

  it('lists a key identified only by `id` and revokes it with that id', async () => {
    mockUseAPIKeys.mockReturnValue({
      data: [{ ...baseKey, id: 'kid-id-spelling' }],
      isLoading: false,
      refetch: vi.fn(),
      error: null,
    });
    mockRevokeMutate.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<AdminPage />);

    expect(await screen.findByText('kid-id-spelling')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Revoke API key' }));
    await user.click(await screen.findByRole('button', { name: 'Revoke Key' }));

    await waitFor(() => {
      expect(mockRevokeMutate).toHaveBeenCalledWith({ keyId: 'kid-id-spelling' });
    });
  });

  it('lists a key identified only by `key_id` and revokes it with that id', async () => {
    mockUseAPIKeys.mockReturnValue({
      data: [
        {
          name: 'Legacy key',
          created_at: '2026-01-01T00:00:00Z',
          key_id: 'kid-key-id-spelling',
        } as unknown as APIKeyResponse,
      ],
      isLoading: false,
      refetch: vi.fn(),
      error: null,
    });
    mockRevokeMutate.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<AdminPage />);

    expect(await screen.findByText('kid-key-id-spelling')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Revoke API key' }));
    await user.click(await screen.findByRole('button', { name: 'Revoke Key' }));

    await waitFor(() => {
      expect(mockRevokeMutate).toHaveBeenCalledWith({ keyId: 'kid-key-id-spelling' });
    });
  });
});
