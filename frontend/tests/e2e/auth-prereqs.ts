const hasUsablePassword = (value: string | undefined): value is string =>
    Boolean(value && value !== 'test-placeholder');

export const hasJwtSigningKey = Boolean(
    process.env.JWT_SIGNING_KEY || process.env.AUTH_SECRET_KEY
);

export const hasPrimaryUserCredentials = Boolean(
    process.env.TEST_USER_EMAIL && hasUsablePassword(process.env.TEST_PASSWORD)
);

export const hasAdminCredentials = Boolean(
    (process.env.TEST_ADMIN_EMAIL && hasUsablePassword(process.env.TEST_ADMIN_PASSWORD)) ||
    hasPrimaryUserCredentials
);

export const hasAuthenticatedE2E = hasJwtSigningKey && hasPrimaryUserCredentials;
export const hasAdminAuthenticatedE2E = hasJwtSigningKey && hasAdminCredentials;

export const authenticatedE2ESkipReason =
    'Set TEST_USER_EMAIL, TEST_PASSWORD, and JWT_SIGNING_KEY (or AUTH_SECRET_KEY) to run authenticated E2E tests.';

// Passwordless login (email OTP) needs the local stack: the backend must run
// with REGENGINE_E2E_MODE=true so the challenges router writes sign-in codes
// to the outbox fixture. External targets (PLAYWRIGHT_BASE_URL) deliver OTPs
// to real inboxes, so completing a login there is not automatable.
export const hasPasswordlessE2E =
    !process.env.PLAYWRIGHT_BASE_URL &&
    process.env.REGENGINE_E2E_MODE?.trim().toLowerCase() === 'true' &&
    Boolean(process.env.TEST_USER_EMAIL);

export const passwordlessE2ESkipReason =
    'Passwordless login E2E requires the local stack (REGENGINE_E2E_MODE=true backend with the OTP outbox fixture).';

export const adminAuthenticatedE2ESkipReason =
    'Set TEST_ADMIN_EMAIL/TEST_ADMIN_PASSWORD or TEST_USER_EMAIL/TEST_PASSWORD, plus JWT_SIGNING_KEY (or AUTH_SECRET_KEY), to run admin-authenticated E2E tests.';
