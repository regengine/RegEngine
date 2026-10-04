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
import {
  OTP_CHALLENGE_STORAGE_KEY,
  saveOtpChallengeState,
} from '@/lib/passwordless-auth';

const mocks = vi.hoisted(() => ({
  seedPasswordlessClientUser: vi.fn(),
  verifyEmailChallenge: vi.fn(),
  clearOtpChallengeState: vi.fn(),
}));

// Only the network call and the profile seeding are stubbed. The sessionStorage
// helpers stay real: that is how /login hands the challenge to /auth/verify,
// and the production path (?next= with no email in the URL) depends on it.
vi.mock('@/lib/passwordless-auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/passwordless-auth')>();
  return {
    ...actual,
    seedPasswordlessClientUser: mocks.seedPasswordlessClientUser,
    verifyEmailChallenge: mocks.verifyEmailChallenge,
    // A spy that still clears the real storage, so the tests can see it cleared.
    clearOtpChallengeState: mocks.clearOtpChallengeState.mockImplementation(
      actual.clearOtpChallengeState,
    ),
  };
});

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

// This is the path production takes. /login saves the challenge to
// sessionStorage and pushes /auth/verify?next=... with no email or
// challenge_id in the URL, so VerifyClient gets initialEmail='' and must load
// the challenge from sessionStorage in its effect. The tests above always put
// the email in the URL and never reach that effect.
describe('/auth/verify page: the challenge comes from sessionStorage, as after /login', () => {
  const EMAIL = 'user@example.com';

  /** The page exactly as /login leaves it: only ?next= in the URL. */
  async function renderPageAsAfterLogin(next?: string) {
    const element = await VerifyPage({
      searchParams: Promise.resolve(next === undefined ? {} : { next }),
    });
    return render(element);
  }

  function storeChallengeAsLoginDoes() {
    saveOtpChallengeState({ email: EMAIL, challengeId: CHALLENGE_ID, createdAt: Date.now() });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    mocks.verifyEmailChallenge.mockResolvedValue(undefined);
  });

  afterEach(() => {
    window.sessionStorage.clear();
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  });

  it('forwards ?next=/developer/portal using the stored challenge, then clears it', async () => {
    storeChallengeAsLoginDoes();
    const assign = mockLocationAssign();
    await renderPageAsAfterLogin('/developer/portal');

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('/developer/portal');
    });
    expect(assign).toHaveBeenCalledTimes(1);
    expect(mocks.verifyEmailChallenge).toHaveBeenCalledWith(CHALLENGE_ID, '123456');
    expect(mocks.seedPasswordlessClientUser).toHaveBeenCalledWith(EMAIL);
    expect(window.sessionStorage.getItem(OTP_CHALLENGE_STORAGE_KEY)).toBeNull();
  });

  it('assigns /dashboard using the stored challenge when there is no ?next=', async () => {
    storeChallengeAsLoginDoes();
    const assign = mockLocationAssign();
    await renderPageAsAfterLogin();

    await enterCode();

    await waitFor(() => {
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
    expect(assign).toHaveBeenCalledTimes(1);
    expect(mocks.verifyEmailChallenge).toHaveBeenCalledWith(CHALLENGE_ID, '123456');
  });

  it('cannot submit and does not navigate when ?next= is set but no challenge is stored', async () => {
    const assign = mockLocationAssign();
    await renderPageAsAfterLogin('/developer/portal');

    expect(screen.getByRole('button', { name: /verify and continue/i })).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent(/could not find a challenge id/i);
    expect(mocks.verifyEmailChallenge).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });
});
