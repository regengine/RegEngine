/**
 * /auth/verify must send a signed-in visitor on to the `next` path they were
 * headed for, and must never forward to anything but a plain same-app path.
 * `next` is validated twice: by the page, from the query string, and again by
 * VerifyClient at the location.assign() sink. Each layer is tested alone so a
 * regression in one cannot hide behind the other.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import VerifyClient from '@/app/auth/verify/VerifyClient';
import VerifyPage from '@/app/auth/verify/page';

const mocks = vi.hoisted(() => ({
  seedPasswordlessClientUser: vi.fn(),
  verifyEmailChallenge: vi.fn(),
  clearOtpChallengeState: vi.fn(),
}));

vi.mock('@/lib/passwordless-auth', () => ({
  seedPasswordlessClientUser: mocks.seedPasswordlessClientUser,
  verifyEmailChallenge: mocks.verifyEmailChallenge,
  clearOtpChallengeState: mocks.clearOtpChallengeState,
  loadOtpChallengeState: vi.fn(() => null),
}));

const CHALLENGE_ID = '11111111-1111-4111-8111-111111111111';

// Same hostile shapes the login tests use: each one is read by a browser as
// another origin, or as a page that would loop back into the sign-in flow.
const UNSAFE_NEXT: [string, string][] = [
  ['protocol-relative', '//evil.com'],
  ['TAB between slashes', '/\t/evil.com'],
  ['LF between slashes', '/\n/evil.com'],
  ['CR between slashes', '/\r/evil.com'],
  ['backslash host', '/\\evil.com'],
  ['dot-segment collapses to //', '/.//evil.com'],
  ['encoded dot-dot collapses to //', '/%2e%2e//evil.com'],
  ['leading space', ' //evil.com'],
  ['absolute URL', 'https://evil.com'],
  ['javascript scheme', 'javascript:alert(1)'],
  ['the login page', '/login'],
  ['the verify page', '/auth/verify'],
  ['empty', ''],
];

const SAFE_NEXT = [
  '/developer/portal',
  '/developer/portal/keys',
  '/dashboard/settings?tab=api#keys',
];

const originalLocation = window.location;

function mockLocationAssign() {
  const assign = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...originalLocation, assign },
  });
  return assign;
}

async function enterCode(): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/verification code/i), '123456');
  await user.click(screen.getByRole('button', { name: /verify and continue/i }));
}

function renderClient(nextPath?: string) {
  return render(
    <VerifyClient initialEmail="user@example.com" initialChallengeId={CHALLENGE_ID} nextPath={nextPath} />,
  );
}

type VerifySearchParams = { email?: string; challenge_id?: string; next?: string | string[] };

/** Run the real server page and render the element tree it returns. */
async function renderPage(searchParams: VerifySearchParams) {
  const element = await VerifyPage({
    searchParams: Promise.resolve({
      email: 'user@example.com',
      challenge_id: CHALLENGE_ID,
      ...searchParams,
    }),
  });
  return render(element);
}

describe('VerifyClient: the location.assign() sink', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.verifyEmailChallenge.mockResolvedValue(undefined);
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  });

  it.each(SAFE_NEXT)('assigns the safe next path %s after a successful code', async (next) => {
    const assign = mockLocationAssign();
    renderClient(next);

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(next);
    });
    expect(assign).toHaveBeenCalledTimes(1);
    expect(mocks.verifyEmailChallenge).toHaveBeenCalledWith(CHALLENGE_ID, '123456');
  });

  it('assigns /dashboard when no next path is given', async () => {
    const assign = mockLocationAssign();
    renderClient();

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
    expect(assign).toHaveBeenCalledTimes(1);
  });

  it.each(UNSAFE_NEXT)(
    'assigns /dashboard, not the unsafe prop (%s), even if the page validation were bypassed',
    async (_label, unsafe) => {
      const assign = mockLocationAssign();
      renderClient(unsafe);

      await enterCode();

      await waitFor(() => {
        expect(assign).toHaveBeenCalledWith('/dashboard');
      });
      expect(assign).not.toHaveBeenCalledWith(unsafe);
      expect(assign).toHaveBeenCalledTimes(1);
    },
  );

  it('does not navigate anywhere when the code is wrong, whatever next says', async () => {
    mocks.verifyEmailChallenge.mockRejectedValueOnce({ response: { status: 401 } });
    const assign = mockLocationAssign();
    renderClient('/developer/portal');

    await enterCode();

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect or expired/i);
    expect(assign).not.toHaveBeenCalled();
    expect(mocks.clearOtpChallengeState).not.toHaveBeenCalled();
  });
});

describe('/auth/verify page: validates next from the query string', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.verifyEmailChallenge.mockResolvedValue(undefined);
  });

  afterEach(() => {
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  });

  it.each(SAFE_NEXT)('forwards ?next=%s through to the assign after a successful code', async (next) => {
    const assign = mockLocationAssign();
    await renderPage({ next });

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith(next);
    });
    expect(assign).toHaveBeenCalledTimes(1);
  });

  it('assigns /dashboard when ?next= is missing', async () => {
    const assign = mockLocationAssign();
    await renderPage({});

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
  });

  it.each(UNSAFE_NEXT)('sanitizes a tampered ?next= (%s) to /dashboard', async (_label, unsafe) => {
    const assign = mockLocationAssign();
    await renderPage({ next: unsafe });

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
    expect(assign).not.toHaveBeenCalledWith(unsafe);
    expect(assign).toHaveBeenCalledTimes(1);
  });

  // ?next=a&next=b reaches a server page as an array. safeNextPath would throw
  // on it (an array has no startsWith), so the page must not hand it over raw.
  it('uses the first value of a repeated ?next=, like /login does', async () => {
    const assign = mockLocationAssign();
    await renderPage({ next: ['/developer/portal', '//evil.com'] });

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('/developer/portal');
    });
    expect(assign).not.toHaveBeenCalledWith('//evil.com');
  });

  it('does not let a safe second value rescue an unsafe first value', async () => {
    const assign = mockLocationAssign();
    await renderPage({ next: ['//evil.com', '/developer/portal'] });

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
    expect(assign).not.toHaveBeenCalledWith('//evil.com');
  });

  it('hands VerifyClient the already-validated path, so a bad value never reaches the sink', async () => {
    const element = await VerifyPage({
      searchParams: Promise.resolve({ next: '/\t/evil.com' }),
    });
    // Suspense > VerifyClient: read the prop the page computed.
    const client = (element.props as { children: { props: { nextPath?: string } } }).children;

    expect(client.props.nextPath).toBe('/dashboard');
  });
});
