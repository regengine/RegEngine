import { expect, test, type Browser, type Page, type TestInfo } from '@playwright/test';
import { exec } from 'node:child_process';
import { promisify } from 'node:util';

const execAsync = promisify(exec);

const REQUIRED_ENV = [
    'LIVE_PASSWORD_RESET_QA',
    'LIVE_PASSWORD_RESET_QA_FRONTEND_URL',
    'NEXT_PUBLIC_SUPABASE_URL',
    'NEXT_PUBLIC_SUPABASE_ANON_KEY',
    'LIVE_PASSWORD_RESET_QA_EMAIL',
    'LIVE_PASSWORD_RESET_QA_NEW_PASSWORD',
    'LIVE_PASSWORD_RESET_QA_MAILBOX_FETCH_COMMAND',
] as const;

type MailMessage = {
    subject?: string;
    text?: string;
    html?: string;
    receivedAt?: string;
};

type QaSummary = {
    covered: string[];
    manual: string[];
    observed: Record<string, unknown>;
};

const enabled = process.env.LIVE_PASSWORD_RESET_QA === 'true';
const missingEnv = REQUIRED_ENV.filter((name) => !process.env[name]);
const qaEmail = process.env.LIVE_PASSWORD_RESET_QA_EMAIL || '';
const newPasswordBase = process.env.LIVE_PASSWORD_RESET_QA_NEW_PASSWORD || '';
const passwordRunId =
    process.env.LIVE_PASSWORD_RESET_QA_PASSWORD_RUN_ID || Date.now().toString(36);
const mailboxCommand = process.env.LIVE_PASSWORD_RESET_QA_MAILBOX_FETCH_COMMAND || '';
const frontendUrl = process.env.LIVE_PASSWORD_RESET_QA_FRONTEND_URL || '';
const mailboxTimeoutMs = Number(process.env.LIVE_PASSWORD_RESET_QA_MAILBOX_TIMEOUT_MS || 60_000);

test.describe('live password reset QA', () => {
    test('validates reset email delivery, fresh-context link use, one-time reuse failure, and confirmation email', async ({
        browser,
        page,
    }, testInfo) => {
        test.skip(
            !enabled,
            `Set LIVE_PASSWORD_RESET_QA=true and provide ${REQUIRED_ENV.join(', ')} to run live password reset QA.`,
        );
        test.skip(
            missingEnv.length > 0,
            `Missing env for live password reset QA: ${missingEnv.join(', ')}`,
        );

        const summary: QaSummary = {
            covered: [
                'reset email arrives for an existing user within 60 seconds',
                'reset link opens in a fresh browser context with no existing session',
                'reset link is single-use after a successful reset',
                'expired/reused link UX is clear for invalid or consumed links',
                'confirmation email arrives after successful reset',
            ],
            manual: [
                'True time-based expiry requires lowering the Supabase recovery-link TTL or waiting past the configured TTL.',
                'Successive reset request semantics must be confirmed against the project Supabase Auth setting: only latest valid, or all issued links valid until expiry.',
                'Token/email binding should be verified in Supabase Auth logs or by confirming the recovery session user id/email before password update.',
                'Existing-session invalidation should be verified with a pre-authenticated browser context for the QA user.',
            ],
            observed: {},
        };
        const newPassword = buildRunPassword(newPasswordBase, passwordRunId);
        summary.observed.passwordRunId = passwordRunId;

        const requestedAfter = new Date();
        await requestPasswordReset(page, qaEmail);
        const resetMessage = await waitForMailboxMessage({
            since: requestedAfter,
            kind: 'password_reset',
            timeoutMs: mailboxTimeoutMs,
            predicate: (message) => Boolean(extractResetUrl(message)),
        });
        const resetUrl = extractResetUrl(resetMessage);
        expect(resetUrl, 'reset email should contain a password reset link').toBeTruthy();
        summary.observed.resetEmailReceivedAt = resetMessage.receivedAt || null;
        summary.observed.resetEmailSubject = resetMessage.subject || null;

        const fresh = await openFreshResetContext(browser, resetUrl || '');
        const confirmationAfter = new Date();
        try {
            await completeReset(fresh.page, newPassword);
        } finally {
            await fresh.close();
        }

        const confirmationMessage = await waitForMailboxMessage({
            since: confirmationAfter,
            kind: 'password_changed_confirmation',
            timeoutMs: mailboxTimeoutMs,
            predicate: (message) => looksLikeConfirmation(message),
        });
        summary.observed.confirmationEmailReceivedAt = confirmationMessage.receivedAt || null;
        summary.observed.confirmationEmailSubject = confirmationMessage.subject || null;

        const reused = await openFreshResetContext(browser, resetUrl || '');
        try {
            await expectExpiredOrInvalidUx(reused.page);
        } finally {
            await reused.close();
        }

        await testInfo.attach('password-reset-live-qa-summary', {
            body: JSON.stringify(summary, null, 2),
            contentType: 'application/json',
        });
    });
});

function buildRunPassword(base: string, runId: string): string {
    const suffix = `-${runId}`;
    if (base.length + suffix.length <= 128) {
        return `${base}${suffix}`;
    }
    return `${base.slice(0, 128 - suffix.length)}${suffix}`;
}

async function requestPasswordReset(page: Page, email: string) {
    await page.goto('/forgot-password');
    await expect(page.getByRole('heading', { name: /reset your password/i })).toBeVisible();
    await page.getByLabel(/^email$/i).fill(email);
    await page.getByRole('button', { name: /send reset link/i }).click();
    await expect(page.getByText(/check your inbox/i)).toBeVisible({ timeout: 20_000 });
}

async function openFreshResetContext(browser: Browser, resetUrl: string) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto(resetUrl);

    const continueButton = page.getByRole('button', { name: /continue to reset password/i });
    if (await continueButton.isVisible({ timeout: 10_000 }).catch(() => false)) {
        await continueButton.click();
    }

    return {
        page,
        close: () => context.close(),
    };
}

async function completeReset(page: Page, password: string) {
    await expect(page.getByRole('heading', { name: /set new password/i })).toBeVisible({ timeout: 30_000 });
    await page.getByLabel(/^new password$/i).fill(password);
    await page.getByLabel(/^confirm new password$/i).fill(password);
    await page.getByRole('button', { name: /update password/i }).click();
    await expect(page.getByText(/password updated/i)).toBeVisible({ timeout: 30_000 });
}

async function expectExpiredOrInvalidUx(page: Page) {
    const expiredCopy = page.getByText(/reset link expired|invalid reset link|expired|request a new link/i).first();
    const continueButton = page.getByRole('button', { name: /continue to reset password/i });

    if (await continueButton.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await continueButton.click();
    }

    await expect(expiredCopy).toBeVisible({ timeout: 20_000 });
}

async function waitForMailboxMessage(options: {
    since: Date;
    kind: string;
    timeoutMs: number;
    predicate: (message: MailMessage) => boolean;
}): Promise<MailMessage> {
    const deadline = Date.now() + options.timeoutMs;
    let lastError = '';

    while (Date.now() < deadline) {
        const messages = await fetchMailboxMessages(options.since, options.kind).catch((error: Error) => {
            lastError = error.message;
            return [];
        });

        const match = messages.find(options.predicate);
        if (match) {
            return match;
        }

        await new Promise((resolve) => setTimeout(resolve, 5_000));
    }

    throw new Error(
        `No ${options.kind} email for ${qaEmail} within ${options.timeoutMs}ms. Last mailbox error: ${lastError || 'none'}`,
    );
}

async function fetchMailboxMessages(since: Date, kind: string): Promise<MailMessage[]> {
    const { stdout, stderr } = await execAsync(mailboxCommand, {
        env: {
            ...process.env,
            LIVE_PASSWORD_RESET_QA_EMAIL: qaEmail,
            LIVE_PASSWORD_RESET_QA_SINCE_ISO: since.toISOString(),
            LIVE_PASSWORD_RESET_QA_MESSAGE_KIND: kind,
        },
        maxBuffer: 1024 * 1024 * 5,
    });

    if (stderr.trim()) {
        console.warn(`[password-reset-live] mailbox command stderr: ${stderr.trim()}`);
    }

    const parsed = JSON.parse(stdout) as MailMessage[] | { messages?: MailMessage[] };
    if (Array.isArray(parsed)) {
        return parsed;
    }
    return parsed.messages || [];
}

function extractResetUrl(message: MailMessage): string | null {
    const body = `${message.html || ''}\n${message.text || ''}`;
    const urls = body.match(/https?:\/\/[^\s"'<>]+/g) || [];
    const frontendOrigin = frontendUrl ? new URL(frontendUrl).origin : '';
    const resetUrl = urls.find((url) => {
        const decoded = decodeHtml(url);
        return (
            decoded.includes('/auth/verify') ||
            decoded.includes('/auth/callback') ||
            decoded.includes('/reset-password') ||
            decoded.includes('/auth/v1/verify')
        ) && (!frontendOrigin || decoded.startsWith(frontendOrigin) || decoded.includes('/auth/v1/verify'));
    });

    return resetUrl ? decodeHtml(resetUrl) : null;
}

function looksLikeConfirmation(message: MailMessage): boolean {
    const haystack = `${message.subject || ''}\n${message.text || ''}\n${message.html || ''}`.toLowerCase();
    return (
        haystack.includes('password') &&
        (haystack.includes('changed') ||
            haystack.includes('updated') ||
            haystack.includes('reset') ||
            haystack.includes('success'))
    );
}

function decodeHtml(value: string): string {
    return value
        .replace(/&amp;/g, '&')
        .replace(/&#x2F;/g, '/')
        .replace(/&#x3D;/g, '=')
        .replace(/&quot;/g, '"');
}
