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
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    });

    it('accepts a well-formed submission', async () => {
        const res = await POST(makeRequest(valid, '198.51.100.10'));
        expect(res.status).toBe(200);
        expect(await res.json()).toEqual({ ok: true });
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

        const res = await POST(makeRequest(valid, '198.51.100.201'));

        expect(res.status).toBe(503);
        expect(fetch).not.toHaveBeenCalled();
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
