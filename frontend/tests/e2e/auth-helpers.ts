import { expect, type BrowserContext, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, rmSync } from 'node:fs';
import path from 'node:path';

export const AUTH_SESSION_COOKIE = '__Host-regengine_session';

type OutboxRecord = {
    kind?: string;
    email?: string;
    code?: string;
    challenge_id?: string;
    created_at?: string;
};

type SessionResponse = {
    authenticated?: boolean;
    auth_method?: string | null;
    user?: { email?: string } | null;
};

type SeedOptions = {
    isSysadmin?: boolean;
};

type VirtualAuthenticatorHandle = {
    authenticatorId: string;
    remove: () => Promise<void>;
};

function repoRoot(): string {
    return path.resolve(process.cwd(), '..');
}

function pythonBin(): string {
    const configuredPython = process.env.PYTHON_BIN;
    if (configuredPython) return configuredPython;
    const repoPython = path.join(repoRoot(), 'venv/bin/python');
    return existsSync(repoPython) ? repoPython : 'python3';
}

export function outboxPath(): string {
    return process.env.REGENGINE_E2E_EMAIL_OUTBOX || '/tmp/regengine-playwright-email-outbox.jsonl';
}

export function resetOtpOutbox(): void {
    rmSync(outboxPath(), { force: true });
}

export function seedPasswordlessUser(email: string, options: SeedOptions = {}): void {
    execFileSync(
        pythonBin(),
        [path.join(repoRoot(), 'scripts/seed_passwordless_e2e_user.py')],
        {
            cwd: repoRoot(),
            env: {
                ...process.env,
                REGENGINE_E2E_MODE: 'true',
                REGENGINE_E2E_IS_SYSADMIN: options.isSysadmin ? 'true' : 'false',
                TEST_USER_EMAIL: email,
            },
        },
    );
}

function readOutboxRecords(): OutboxRecord[] {
    const file = outboxPath();
    if (!existsSync(file)) return [];
    return readFileSync(file, 'utf-8')
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => JSON.parse(line) as OutboxRecord);
}

async function waitForOtp(email: string): Promise<string> {
    const deadline = Date.now() + 10_000;
    while (Date.now() < deadline) {
        const record = readOutboxRecords()
            .reverse()
            .find((candidate) => (
                candidate.kind === 'auth_challenge'
                && candidate.email === email
                && typeof candidate.code === 'string'
                && /^\d{6}$/.test(candidate.code)
            ));
        if (record?.code) return record.code;
        await new Promise((resolve) => setTimeout(resolve, 250));
    }
    throw new Error(`Timed out waiting for OTP outbox record for ${email}`);
}

export async function loginWithEmailOtp(
    page: Page,
    context: BrowserContext,
    email: string,
): Promise<void> {
    await context.clearCookies();

    await page.goto('/login');
    await expect(page.getByRole('heading', { name: /continue to regengine/i })).toBeVisible();

    await page.getByLabel(/email address/i).fill(email);
    await page.getByRole('button', { name: /^continue/i }).click();
    await expect(page).toHaveURL(/\/auth\/verify$/);

    const otp = await waitForOtp(email);
    await page.getByLabel(/verification code/i).fill(otp);
    await page.getByRole('button', { name: /verify and continue/i }).click();
    await expect(page).toHaveURL(/\/dashboard$/);

    const cookies = await context.cookies();
    const sessionCookie = cookies.find((cookie) => cookie.name === AUTH_SESSION_COOKIE);
    expect(sessionCookie, 'opaque session cookie is present').toBeTruthy();
    expect(sessionCookie?.httpOnly).toBe(true);
    expect(sessionCookie?.secure).toBe(true);
    expect(sessionCookie?.sameSite).toBe('Lax');
    expect(sessionCookie?.path).toBe('/');
}

export async function expectHydratedSession(
    page: Page,
    email: string,
    authMethod: 'email_otp' | 'webauthn' | 'sso',
): Promise<void> {
    await expect.poll(async () => {
        const response = await page.request.get('/api/session');
        if (!response.ok()) return false;
        const body = await response.json() as SessionResponse;
        return body.authenticated === true
            && body.auth_method === authMethod
            && body.user?.email === email;
    }, {
        message: `opaque session hydrates as ${authMethod}`,
        timeout: 10_000,
    }).toBe(true);
}

export async function enableVirtualAuthenticator(page: Page): Promise<VirtualAuthenticatorHandle> {
    const cdpSession = await page.context().newCDPSession(page);
    await cdpSession.send('WebAuthn.enable');
    const { authenticatorId } = await cdpSession.send('WebAuthn.addVirtualAuthenticator', {
        options: {
            protocol: 'ctap2',
            transport: 'internal',
            hasResidentKey: false,
            hasUserVerification: true,
            isUserVerified: true,
            automaticPresenceSimulation: true,
        },
    });

    return {
        authenticatorId,
        remove: async () => {
            await cdpSession.send('WebAuthn.removeVirtualAuthenticator', { authenticatorId }).catch(() => undefined);
            await cdpSession.detach().catch(() => undefined);
        },
    };
}
