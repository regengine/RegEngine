/**
 * /api/contact abuse controls (#2449 low):
 *   1. Honeypot — a filled `website` field is silently dropped (fake success)
 *      so bots that auto-fill every field don't reach the webhook/log.
 *   2. Per-IP rate limit — best-effort in-memory throttle returns 429 after
 *      the burst threshold for a given IP.
 */
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { POST } from '@/app/api/contact/route';

function makeRequest(
    body: Record<string, unknown>,
    ip = '203.0.113.1',
): Request {
    return new Request('http://localhost/api/contact', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'x-forwarded-for': ip,
        },
        body: JSON.stringify(body),
    });
}

const valid = { name: 'Ada', email: 'ada@example.com', message: 'hello' };

describe('POST /api/contact abuse controls', () => {
    beforeEach(() => {
        process.env.CONTACT_WEBHOOK_URL = 'https://contact-provider.example/submit';
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    });

    afterEach(() => {
        delete process.env.CONTACT_WEBHOOK_URL;
        delete process.env.RESEND_API_KEY;
        delete process.env.RESEND_FROM_EMAIL;
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    });

    it('accepts a well-formed submission', async () => {
        const res = await POST(makeRequest(valid, '198.51.100.10'));
        expect(res.status).toBe(200);
        expect(await res.json()).toEqual({ ok: true });
    });

    it('forwards normalized UTM fields to the webhook without logging them', async () => {
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
        const res = await POST(makeRequest({
            ...valid,
            utm_source: '  CampaignSource  ',
            utm_medium: ' Email ',
            utm_campaign: 'A'.repeat(110),
        }, '198.51.100.13'));

        expect(res.status).toBe(200);
        const [, options] = vi.mocked(fetch).mock.calls[0];
        const submission = JSON.parse(options?.body as string);
        expect(submission).toMatchObject({
            utm_source: 'campaignsource',
            utm_medium: 'email',
            utm_campaign: 'a'.repeat(100),
        });
        expect(JSON.stringify(warn.mock.calls)).not.toContain('campaignsource');
    });

    it('drops honeypot submissions with a fake success', async () => {
        const res = await POST(
            makeRequest({ ...valid, website: 'http://spam.example' }, '198.51.100.11'),
        );
        expect(res.status).toBe(200);
        expect(await res.json()).toEqual({ ok: true });
    });

    it('still validates required fields', async () => {
        const res = await POST(makeRequest({ email: 'a@b.co' }, '198.51.100.12'));
        expect(res.status).toBe(400);
    });

    it('rate-limits a single IP after the burst threshold', async () => {
        const ip = '198.51.100.99';
        // First 5 are allowed; the 6th within the window is rejected.
        for (let i = 0; i < 5; i++) {
            const ok = await POST(makeRequest(valid, ip));
            expect(ok.status).toBe(200);
        }
        const blocked = await POST(makeRequest(valid, ip));
        expect(blocked.status).toBe(429);
        expect(blocked.headers.get('Retry-After')).toBe('600');
    });

    it('keeps separate budgets per IP', async () => {
        const res = await POST(makeRequest(valid, '198.51.100.200'));
        expect(res.status).toBe(200);
    });

    it('fails closed when delivery is not configured', async () => {
        delete process.env.CONTACT_WEBHOOK_URL;
        delete process.env.RESEND_API_KEY;

        const res = await POST(makeRequest(valid, '198.51.100.201'));

        expect(res.status).toBe(503);
        expect(await res.json()).toEqual({ error: 'contact_service_unavailable' });
        expect(fetch).not.toHaveBeenCalled();
    });

    it('delivers via Resend when no webhook is configured', async () => {
        delete process.env.CONTACT_WEBHOOK_URL;
        delete process.env.RESEND_FROM_EMAIL;
        process.env.RESEND_API_KEY = 'test-resend-key'; // pragma: allowlist secret
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

        const res = await POST(makeRequest({
            ...valid,
            company: 'Line\r\nBreak Co',
            message: 'Need access',
            utm_source: 'ads',
        }, '198.51.100.210'));

        expect(res.status).toBe(200);
        expect(await res.json()).toEqual({ ok: true });
        expect(fetch).toHaveBeenCalledTimes(1);
        const [url, options] = vi.mocked(fetch).mock.calls[0];
        expect(url).toBe('https://api.resend.com/emails');
        expect(options).toEqual(expect.objectContaining({
            method: 'POST',
            redirect: 'manual',
            headers: {
                Authorization: 'Bearer test-resend-key',
                'Content-Type': 'application/json',
            },
        }));
        expect(options?.signal).toBeInstanceOf(AbortSignal);
        const body = JSON.parse(options?.body as string);
        expect(body.to).toEqual(['christopher@regengine.co']);
        expect(body.reply_to).toBe('ada@example.com');
        expect(body.from).toBe('RegEngine <onboarding@regengine.co>');
        expect(body.subject).toBe('RegEngine request: LineBreak Co');
        expect(body.subject).not.toMatch(/[\r\n]/);
        expect(body.text).toContain('submission_id: ');
        expect(body.text).toContain('source: regengine.co/contact');
        expect(body.text).toContain('name: Ada');
        expect(body.text).toContain('email: ada@example.com');
        expect(body.text).toContain('company: Line\r\nBreak Co');
        expect(body.text).toContain('utm_source: ads');
        expect(body.text).toContain('message: Need access');
        expect(JSON.stringify(warn.mock.calls)).toContain('"provider":"resend"');
        expect(JSON.stringify(warn.mock.calls)).not.toContain('ada@example.com');
    });

    it('returns 502 when Resend refuses the email', async () => {
        delete process.env.CONTACT_WEBHOOK_URL;
        process.env.RESEND_API_KEY = 'test-resend-key'; // pragma: allowlist secret
        vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 422 }));
        const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);

        const res = await POST(makeRequest(valid, '198.51.100.211'));

        expect(res.status).toBe(502);
        expect(await res.json()).toEqual({ error: 'contact_delivery_failed' });
        expect(JSON.stringify(error.mock.calls)).toContain('"provider":"resend"');
        expect(JSON.stringify(error.mock.calls)).not.toContain('ada@example.com');
    });

    it('prefers the webhook when both providers are configured', async () => {
        process.env.RESEND_API_KEY = 'test-resend-key'; // pragma: allowlist secret

        const res = await POST(makeRequest(valid, '198.51.100.212'));

        expect(res.status).toBe(200);
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(fetch).toHaveBeenCalledWith(
            'https://contact-provider.example/submit',
            expect.objectContaining({ redirect: 'manual' }),
        );
    });

    it('does not follow redirects or log contact PII', async () => {
        vi.mocked(fetch).mockResolvedValueOnce(new Response(null, {
            status: 307,
            headers: { location: 'http://127.0.0.1/internal' },
        }));
        const info = vi.spyOn(console, 'info').mockImplementation(() => undefined);
        const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
        const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);

        const res = await POST(makeRequest({
            name: 'Private Name',
            email: 'private@example.com',
            company: 'Private Company',
            message: 'private message body',
        }, '198.51.100.202'));

        expect(res.status).toBe(502);
        expect(fetch).toHaveBeenCalledWith(
            'https://contact-provider.example/submit',
            expect.objectContaining({ redirect: 'manual' }),
        );
        const logged = JSON.stringify([...info.mock.calls, ...warn.mock.calls, ...error.mock.calls]);
        expect(logged).not.toContain('Private Name');
        expect(logged).not.toContain('private@example.com');
        expect(logged).not.toContain('Private Company');
        expect(logged).not.toContain('private message body');
    });
});
