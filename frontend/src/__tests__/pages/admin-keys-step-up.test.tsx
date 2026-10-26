import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AdminPage from '@/app/admin/page';
import { StepUpModal } from '@/components/auth/StepUpModal';

const mocks = vi.hoisted(() => ({
  listAPIKeys: vi.fn(),
  performPasskeyLogin: vi.fn(),
  push: vi.fn(),
}));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isHighAssuranceSession: true,
    user: { is_sysadmin: true },
    setApiKey: vi.fn(),
    tenantId: undefined,
  }),
}));
vi.mock('@/lib/api-client', () => ({ apiClient: { listAPIKeys: mocks.listAPIKeys } }));
vi.mock('@/lib/passwordless-auth', () => ({
  isValidEmail: () => true,
  performPasskeyLogin: mocks.performPasskeyLogin,
  seedPasswordlessClientUser: vi.fn(),
}));
vi.mock('@/components/layout/page-container', () => ({
  PageContainer: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminPage />
      <StepUpModal />
    </QueryClientProvider>,
  );
}

describe('Admin keys list step-up', () => {
  beforeEach(() => {
    mocks.listAPIKeys.mockReset();
    mocks.performPasskeyLogin.mockReset().mockResolvedValue(undefined);
    mocks.push.mockReset();
    mocks.listAPIKeys
      .mockRejectedValueOnce(Object.assign(new Error('Forbidden'), {
        response: { status: 403, data: { detail: { code: 'requires_step_up' } } },
      }))
      .mockResolvedValueOnce([]);
  });

  it('shows the passkey notice without opening the dialog on load', async () => {
    renderPage();

    expect(await screen.findByText(/passkey required/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirm with passkey/i })).toBeInTheDocument();
    expect(screen.queryByText(/not authorized to manage live credentials/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('runs step-up from the button and retries the load after success', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /confirm with passkey/i }));
    expect(screen.getByRole('dialog')).toHaveTextContent(/view and manage live api keys/i);

    await user.click(screen.getByRole('button', { name: /authenticate with passkey/i }));

    expect(mocks.performPasskeyLogin).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mocks.listAPIKeys).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/no api keys found/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /confirm with passkey/i })).not.toBeInTheDocument();
  });

  it('returns to the dashboard on Cancel without retrying the blocked load', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /confirm with passkey/i }));
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));

    expect(mocks.push).toHaveBeenCalledWith('/dashboard');
    expect(mocks.performPasskeyLogin).not.toHaveBeenCalled();
    expect(mocks.listAPIKeys).toHaveBeenCalledTimes(1);
  });
});
