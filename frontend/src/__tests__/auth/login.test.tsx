import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import VerifyClient from '@/app/auth/verify/VerifyClient';
import LoginPage from '@/app/login/page';

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  routerRefresh: vi.fn(),
  searchParamGet: vi.fn(),
  startEmailChallenge: vi.fn(),
  saveOtpChallengeState: vi.fn(),
  performPasskeyLogin: vi.fn(),
  seedPasswordlessClientUser: vi.fn(),
  verifyEmailChallenge: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mocks.routerPush,
    refresh: mocks.routerRefresh,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => ({
    get: mocks.searchParamGet,
  }),
}));

const authState = vi.hoisted(() => ({
  user: null as { id: string; email: string } | null,
  isAuthenticated: false,
  isHydrated: true,
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => authState,
}));

vi.mock('@/lib/passwordless-auth', () => ({
  isValidEmail: (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim()),
  startEmailChallenge: mocks.startEmailChallenge,
  saveOtpChallengeState: mocks.saveOtpChallengeState,
  performPasskeyLogin: mocks.performPasskeyLogin,
  seedPasswordlessClientUser: mocks.seedPasswordlessClientUser,
  verifyEmailChallenge: mocks.verifyEmailChallenge,
  clearOtpChallengeState: vi.fn(),
  loadOtpChallengeState: vi.fn(() => null),
}));

function mockLocationAssign() {
  const originalLocation = window.location;
  const assign = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      ...originalLocation,
      assign,
    },
  });
  return assign;
}

describe('passwordless login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = null;
    authState.isAuthenticated = false;
    authState.isHydrated = true;
    mocks.searchParamGet.mockReturnValue(null);
    mocks.startEmailChallenge.mockResolvedValue({
      detail: 'If this address is eligible, a sign-in code is on its way.',
      challenge_id: '11111111-1111-4111-8111-111111111111',
    });
    mocks.performPasskeyLogin.mockResolvedValue(undefined);
    mocks.verifyEmailChallenge.mockResolvedValue(undefined);
  });

  it('does not auto-forward on stale localStorage user without a cookie session (redirect loop regression)', () => {
    // A user object hydrated from localStorage can outlive the re_access_token
    // cookie. Auto-forwarding to ?next= in that state ping-pongs with the
    // server-side auth gate on the target page (login -> portal -> login ...).
    authState.user = { id: 'stale', email: 'stale@example.com' };
    authState.isAuthenticated = false;
    mocks.searchParamGet.mockImplementation((key: string) =>
      key === 'next' ? '/developer/portal' : null,
    );

    render(<LoginPage />);

    expect(mocks.routerPush).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it('auto-forwards to the next path when the cookie session is authenticated', async () => {
    authState.user = { id: 'live', email: 'live@example.com' };
    authState.isAuthenticated = true;
    mocks.searchParamGet.mockImplementation((key: string) =>
      key === 'next' ? '/developer/portal' : null,
    );

    render(<LoginPage />);

    await waitFor(() => {
      expect(mocks.routerPush).toHaveBeenCalledWith('/developer/portal');
    });
  });

  it('renders a single email entry point with passkey sign-in and no password field', () => {
    render(<LoginPage />);

    expect(screen.getByRole('heading', { name: /continue to regengine/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^continue/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in with passkey/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/^password$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /create an account/i })).not.toBeInTheDocument();
  });

  it('starts an OTP challenge and routes to the verification screen', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'User@Example.com');
    await user.click(screen.getByRole('button', { name: /^continue/i }));

    await waitFor(() => {
      expect(mocks.startEmailChallenge).toHaveBeenCalledWith('user@example.com');
      expect(mocks.saveOtpChallengeState).toHaveBeenCalledWith({
        email: 'user@example.com',
        challengeId: '11111111-1111-4111-8111-111111111111',
        createdAt: expect.any(Number),
      });
      expect(mocks.routerPush).toHaveBeenCalledWith('/auth/verify');
    });
  });

  it('redirects immediately when the backend requires SSO', async () => {
    const assign = mockLocationAssign();
    mocks.startEmailChallenge.mockResolvedValueOnce({
      message: 'Organization requires Single Sign-On.',
      sso_redirect: true,
      organization_id: 'org-123',
    });
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'person@sso.example');
    await user.click(screen.getByRole('button', { name: /^continue/i }));

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('/auth/sso/mock?organization_id=org-123');
      expect(mocks.saveOtpChallengeState).not.toHaveBeenCalled();
    });
  });

  it('prompts for email and starts passkey login', async () => {
    const assign = mockLocationAssign();
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByRole('button', { name: /sign in with passkey/i }));
    await user.type(screen.getByLabelText(/passkey email/i), 'passkey@example.com');
    const passkeyButtons = screen.getAllByRole('button', { name: /sign in with passkey/i });
    await user.click(passkeyButtons[passkeyButtons.length - 1]);

    await waitFor(() => {
      expect(mocks.performPasskeyLogin).toHaveBeenCalledWith('passkey@example.com');
      expect(mocks.seedPasswordlessClientUser).toHaveBeenCalledWith('passkey@example.com');
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
  });
});

describe('OTP verification', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.verifyEmailChallenge.mockResolvedValue(undefined);
  });

  it('rejects malformed codes before calling the API', async () => {
    const user = userEvent.setup();
    render(
      <VerifyClient
        initialEmail="user@example.com"
        initialChallengeId="11111111-1111-4111-8111-111111111111"
      />,
    );

    await user.type(screen.getByLabelText(/verification code/i), '123');
    await user.click(screen.getByRole('button', { name: /verify and continue/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/6-digit code/i);
    expect(mocks.verifyEmailChallenge).not.toHaveBeenCalled();
  });

  it('verifies the OTP challenge and navigates to the dashboard', async () => {
    const assign = mockLocationAssign();
    const user = userEvent.setup();
    render(
      <VerifyClient
        initialEmail="user@example.com"
        initialChallengeId="11111111-1111-4111-8111-111111111111"
      />,
    );

    await user.type(screen.getByLabelText(/verification code/i), '123456');
    await user.click(screen.getByRole('button', { name: /verify and continue/i }));

    await waitFor(() => {
      expect(mocks.verifyEmailChallenge).toHaveBeenCalledWith(
        '11111111-1111-4111-8111-111111111111',
        '123456',
      );
      expect(mocks.seedPasswordlessClientUser).toHaveBeenCalledWith('user@example.com');
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
  });

  it('shows inline errors for wrong or expired OTP codes', async () => {
    mocks.verifyEmailChallenge.mockRejectedValueOnce({ response: { status: 401 } });
    const user = userEvent.setup();
    render(
      <VerifyClient
        initialEmail="user@example.com"
        initialChallengeId="11111111-1111-4111-8111-111111111111"
      />,
    );

    await user.type(screen.getByLabelText(/verification code/i), '123456');
    await user.click(screen.getByRole('button', { name: /verify and continue/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect or expired/i);
  });
});
