/**
 * Playwright Global Setup
 *
 * Runs once before any tests. Provisions the E2E test user in the admin
 * service database so that login tests succeed.
 *
 * WHY: The admin service has its own `users` table with bcrypt-hashed
 * passwords. Creating a user in the Supabase dashboard only adds them to
 * Supabase auth — NOT to the admin service DB. Login calls
 * POST /auth/login on the admin service, which looks up users in its own
 * table. This setup step calls POST /auth/signup to create the user in
 * both places idempotently.
 */

export default async function globalSetup() {
    // ── Preflight: verify JWT_SIGNING_KEY is configured ──────────────────
    // Without this key, the Next.js middleware cannot verify JWTs from the
    // admin service and EVERY authenticated test will fail with
    // "session_expired". Fail fast in CI, but allow local no-secret runs to
    // execute unauthenticated specs while auth specs self-skip.
    const isCI = Boolean(process.env.CI);
    const jwtKey = process.env.JWT_SIGNING_KEY || process.env.AUTH_SECRET_KEY;
    if (!jwtKey) {
        const message =
            'JWT_SIGNING_KEY (or AUTH_SECRET_KEY) is not set.\n' +
            '  The Next.js middleware needs this to verify tokens from the admin service.\n' +
            '  Without it, authenticated routes redirect to /login?error=session_expired.\n' +
            '  Local run: authenticated specs will be skipped; unauthenticated specs can still run.\n' +
            '  CI run: add JWT_SIGNING_KEY to GitHub Secrets (must match Railway\'s value).';

        if (isCI) {
            console.error(`[globalSetup] ✗ FATAL: ${message}`);
            throw new Error('JWT_SIGNING_KEY is not configured — all authenticated E2E tests will fail');
        }

        console.warn(`[globalSetup] ${message}`);
        return;
    }
    console.log('[globalSetup] ✓ JWT_SIGNING_KEY is configured');

    const adminServiceUrl =
        process.env.ADMIN_SERVICE_URL ||
        (!isCI ? 'http://localhost:8000' : undefined) ||
        'https://regengine-production.up.railway.app';

    const email = process.env.TEST_USER_EMAIL;
    const password = process.env.TEST_PASSWORD;
    const adminEmail = process.env.TEST_ADMIN_EMAIL;
    const adminPassword = process.env.TEST_ADMIN_PASSWORD;
    const hasDistinctAdmin =
        Boolean(adminEmail && adminPassword) && adminEmail !== email;

    const loginAndReadRole = async (loginEmail: string, loginPassword: string) => {
        const response = await fetch(`${adminServiceUrl}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: loginEmail, password: loginPassword }),
        });

        if (!response.ok) {
            return null;
        }

        const payload = await response.json().catch(() => null);
        return {
            ok: true,
            isSysadmin: Boolean(payload?.user?.is_sysadmin),
        };
    };

    if (hasDistinctAdmin && adminEmail && adminPassword) {
        console.log(`[globalSetup] Bootstrapping sysadmin test user: ${adminEmail}`);

        try {
            const response = await fetch(`${adminServiceUrl}/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: adminEmail,
                    password: adminPassword,
                    tenant_name: 'E2E Sysadmin Org',
                }),
            });

            if (response.ok) {
                console.log(`[globalSetup] ✓ Sysadmin test user created: ${adminEmail}`);
            } else if (response.status === 403) {
                const existingAdmin = await loginAndReadRole(adminEmail, adminPassword);
                if (existingAdmin?.ok && existingAdmin.isSysadmin) {
                    console.log(`[globalSetup] ✓ Sysadmin test user already provisioned: ${adminEmail}`);
                } else {
                    const body = await response.text().catch(() => '');
                    console.warn(
                        `[globalSetup] ⚠ Could not bootstrap sysadmin test user.\n` +
                        `  /auth/register returned 403 and login did not confirm a sysadmin account.\n` +
                        `  Response: ${body}`
                    );
                }
            } else {
                const body = await response.text().catch(() => '');
                console.warn(`[globalSetup] ⚠ Sysadmin bootstrap returned ${response.status}: ${body}`);
            }
        } catch (err) {
            console.warn(
                `[globalSetup] ⚠ Could not bootstrap sysadmin test user.\n` +
                `  Dedicated sysadmin E2E coverage may be skipped or fail.\n` +
                `  Error: ${err}`
            );
        }
    }

    if (!email || !password || password === 'test-placeholder') {
        console.log(
            '[globalSetup] TEST_USER_EMAIL / TEST_PASSWORD not configured — skipping test user provisioning'
        );
        return;
    }

    console.log(`[globalSetup] Provisioning test user: ${email}`);

    try {
        const response = await fetch(`${adminServiceUrl}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email,
                password,
                tenant_name: 'E2E Test Org',
            }),
        });

        if (response.ok) {
            console.log(`[globalSetup] ✓ Test user created: ${email}`);
        } else if (response.status === 409) {
            // User already exists — that's fine, credentials are already in the DB
            console.log(`[globalSetup] ✓ Test user already exists: ${email}`);
        } else if (response.status === 400) {
            const body = await response.text().catch(() => '');
            // Could be duplicate email (some services return 400 for this)
            // or password policy failure
            if (body.toLowerCase().includes('already') || body.toLowerCase().includes('exist')) {
                console.log(`[globalSetup] ✓ Test user already exists: ${email}`);
            } else {
                console.warn(
                    `[globalSetup] ⚠ Signup returned 400 — check TEST_PASSWORD meets policy:\n` +
                    `  - Min 12 characters\n` +
                    `  - Uppercase, lowercase, digit, and special character required\n` +
                    `  Response: ${body}`
                );
            }
        } else {
            const body = await response.text().catch(() => '');
            console.warn(`[globalSetup] ⚠ Signup returned ${response.status}: ${body}`);
        }
    } catch (err) {
        console.warn(
            `[globalSetup] ⚠ Could not reach admin service to provision test user.\n` +
            `  Tests requiring login will fail.\n` +
            `  Error: ${err}`
        );
    }

    // ── Smoke test: login and verify JWT locally ─────────────────────────
    // Catches JWT_SIGNING_KEY mismatches between CI and Railway before
    // 40+ tests waste 10 minutes timing out.
    console.log('[globalSetup] Smoke-testing login + JWT verification...');
    try {
        const loginRes = await fetch(`${adminServiceUrl}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });

        if (!loginRes.ok) {
            console.warn(
                `[globalSetup] ⚠ Login smoke test failed (HTTP ${loginRes.status}). ` +
                `Tests requiring auth will likely fail.`
            );
        } else {
            const loginData = await loginRes.json();
            const token = loginData.access_token;

            if (token) {
                // Verify the JWT with the local signing key
                const { jwtVerify } = await import('jose');
                const secret = new TextEncoder().encode(jwtKey);
                try {
                    await jwtVerify(token, secret, { algorithms: ['HS256'] });
                    console.log('[globalSetup] ✓ JWT verification succeeded — signing keys match');
                } catch (verifyErr) {
                    console.error(
                        `[globalSetup] ✗ FATAL: JWT verification FAILED.\n` +
                        `  The admin service signed a JWT that this Next.js instance cannot verify.\n` +
                        `  This means JWT_SIGNING_KEY in GitHub Secrets does NOT match\n` +
                        `  the JWT_SIGNING_KEY on Railway (admin service).\n` +
                        `  → Copy the exact JWT_SIGNING_KEY from Railway env vars to GitHub Secrets.\n` +
                        `  Error: ${verifyErr}`
                    );
                    throw new Error(
                        'JWT_SIGNING_KEY mismatch: CI key cannot verify admin service tokens'
                    );
                }
            }
        }
    } catch (err) {
        if ((err as Error).message?.includes('JWT_SIGNING_KEY')) {
            throw err; // Re-throw fatal mismatch errors
        }
        console.warn(`[globalSetup] ⚠ Login smoke test skipped: ${err}`);
    }
}
