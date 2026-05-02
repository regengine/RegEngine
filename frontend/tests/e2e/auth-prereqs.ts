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

export const adminAuthenticatedE2ESkipReason =
    'Set TEST_ADMIN_EMAIL/TEST_ADMIN_PASSWORD or TEST_USER_EMAIL/TEST_PASSWORD, plus JWT_SIGNING_KEY (or AUTH_SECRET_KEY), to run admin-authenticated E2E tests.';
