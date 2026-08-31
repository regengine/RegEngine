import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminPage from '@/app/admin/page';

const mockUseAuth = vi.hoisted(() => vi.fn());
const mockUseAPIKeys = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('@/hooks/use-api', () => ({
  useAPIKeys: (enabled: boolean) => mockUseAPIKeys(enabled),
  useCreateAPIKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useGenerateAPIKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRevokeAPIKey: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

describe('AdminPage privileged session gate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAPIKeys.mockReturnValue({
      data: [],
      isLoading: false,
      refetch: vi.fn(),
      error: null,
    });
  });

  it('does not enable live key management for a high-assurance non-sysadmin', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isHighAssuranceSession: true,
      user: { is_sysadmin: false },
      setApiKey: vi.fn(),
      tenantId: 'tenant-1',
    });

    render(<AdminPage />);

    expect(mockUseAPIKeys).toHaveBeenCalledWith(false);
    expect(screen.queryByText('Developer Settings')).not.toBeInTheDocument();
    expect(screen.getByText(/WebAuthn or SSO sysadmin session/i)).toBeInTheDocument();
  });

  it('enables live key management for a high-assurance sysadmin', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isHighAssuranceSession: true,
      user: { is_sysadmin: true },
      setApiKey: vi.fn(),
      tenantId: 'tenant-1',
    });

    render(<AdminPage />);

    expect(mockUseAPIKeys).toHaveBeenCalledWith(true);
    expect(screen.getByText('Developer Settings')).toBeInTheDocument();
  });
});
