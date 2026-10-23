import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import QAHealthPage from '@/app/dashboard/qa-health/page';
import { StepUpModal } from '@/components/auth/StepUpModal';
import { useQAHealth } from '@/hooks/use-api';

const mocks = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ user: { is_sysadmin: true }, isHydrated: true }),
}));
vi.mock('@/hooks/use-api', () => ({ useQAHealth: vi.fn() }));
vi.mock('@/lib/passwordless-auth', () => ({
  isValidEmail: () => true,
  performPasskeyLogin: vi.fn(),
  seedPasswordlessClientUser: vi.fn(),
}));
vi.mock('@/components/layout/page-container', () => ({
  PageContainer: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

describe('QA Health step-up', () => {
  beforeEach(() => {
    mocks.push.mockReset();
    vi.mocked(useQAHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      isRefetching: false,
      refetch: vi.fn(),
      error: Object.assign(new Error('Forbidden'), {
        response: { status: 403, data: { detail: { code: 'requires_step_up' } } },
      }),
    } as unknown as ReturnType<typeof useQAHealth>);
  });

  it('does not open the passkey prompt on page load', () => {
    render(<><QAHealthPage /><StepUpModal /></>);
    expect(screen.getByRole('heading', { name: /passkey confirmation required/i })).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens the prompt with the QA Health reason, and cancel returns to the dashboard', async () => {
    const user = userEvent.setup();
    render(<><QAHealthPage /><StepUpModal /></>);

    await user.click(screen.getByRole('button', { name: /confirm with passkey/i }));
    expect(screen.getByRole('dialog')).toHaveTextContent(/confirm it's you to view qa health/i);

    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mocks.push).toHaveBeenCalledWith('/dashboard');
  });
});
