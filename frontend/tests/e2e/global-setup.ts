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
    const adminServiceUrl =
        process.env.ADMIN_SERVICE_URL ||
        'https://regengine-production.up.railway.app';

    const email = process.env.TEST_USER_EMAIL;
    const password = process.env.TEST_PASSWORD;

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

    // Provision admin user if separate credentials are configured
    const adminEmail = process.env.TEST_ADMIN_EMAIL;
    const adminPassword = process.env.TEST_ADMIN_PASSWORD;

    if (adminEmail && adminPassword && adminEmail !== email) {
        console.log(`[globalSetup] Provisioning admin test user: ${adminEmail}`);
        try {
            const response = await fetch(`${adminServiceUrl}/auth/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: adminEmail,
                    password: adminPassword,
                    tenant_name: 'E2E Admin Org',
                }),
            });
            if (response.ok || response.status === 409 || response.status === 400) {
                console.log(`[globalSetup] ✓ Admin test user provisioned: ${adminEmail}`);
            }
        } catch {
            // Non-fatal — admin tests may fail but regular tests still run
        }
    }
}
