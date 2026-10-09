/**
 * /api/client-errors beacon (WS-10):
 *   1. Well-formed reports are accepted (204, no body) and logged with
 *      truncated, query-stripped fields.
 *   2. Oversized / malformed / empty payloads are dropped silently (204) —
 *      the beacon never errors into the page.
 *   3. Per-IP rate limit returns 429 after the burst threshold.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '@/app/api/client-errors/route';

function makeRequest(body: unknown, ip = '203.0.113.5'): NextRequest {
    return new NextRequest('http://localhost/api/client-errors', {
        method: 'POST',
        headers: {
            'content-type': 'application/json',
            'x-forwarded-for': ip,
        },
        body: typeof body === 'string' ? body : JSON.stringify(body),
    });
}

describe('POST /api/client-errors', () => {
    let errorSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
        errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    });

    afterEach(() => {
        errorSpy.mockRestore();
    });

    it('accepts a report and logs a structured entry', async () => {
        const res = await POST(
            makeRequest(
                {
                    kind: 'error',
                    message: 'boom',
                    stack: 'Error: boom\n  at page.tsx:1',
                    url: 'https://app.example/dashboard',
                },
                '198.51.100.20',
            ),
        );
        expect(res.status).toBe(204);
        expect(errorSpy).toHaveBeenCalledTimes(1);
        const [tag, json] = errorSpy.mock.calls[0];
        expect(tag).toBe('[client-error]');
        const entry = JSON.parse(json as string);
        expect(entry.kind).toBe('error');
        expect(entry.message).toBe('boom');
    });

    it('strips query strings server-side even if the client did not', async () => {
        const res = await POST(
            makeRequest(
                {
                    kind: 'error',
                    message: 'boom',
                    url: 'https://app.example/reset?token=SECRET#frag',
                },
                '198.51.100.21',
            ),
        );
        expect(res.status).toBe(204);
        const entry = JSON.parse(errorSpy.mock.calls[0][1] as string);
        expect(entry.url).toBe('https://app.example/reset');
        expect(entry.url).not.toContain('SECRET');
    });

    it('truncates oversized fields', async () => {
        const res = await POST(
            makeRequest(
                { kind: 'error', message: 'm'.repeat(2000), stack: 's'.repeat(6000) },
                '198.51.100.22',
            ),
        );
        expect(res.status).toBe(204);
        const entry = JSON.parse(errorSpy.mock.calls[0][1] as string);
        expect(entry.message.length).toBeLessThanOrEqual(500);
        expect(entry.stack.length).toBeLessThanOrEqual(4000);
    });

    it('drops malformed JSON silently', async () => {
        const res = await POST(makeRequest('{not json', '198.51.100.23'));
        expect(res.status).toBe(204);
        expect(errorSpy).not.toHaveBeenCalled();
    });

    it('drops reports without a message', async () => {
        const res = await POST(makeRequest({ kind: 'error' }, '198.51.100.24'));
        expect(res.status).toBe(204);
        expect(errorSpy).not.toHaveBeenCalled();
    });

    it('drops oversized bodies silently', async () => {
        const res = await POST(
            makeRequest({ kind: 'error', message: 'x'.repeat(10_000) }, '198.51.100.25'),
        );
        expect(res.status).toBe(204);
        expect(errorSpy).not.toHaveBeenCalled();
    });

    it('rate-limits a single IP after the burst threshold', async () => {
        const ip = '198.51.100.99';
        for (let i = 0; i < 10; i++) {
            const res = await POST(makeRequest({ kind: 'error', message: `e${i}` }, ip));
            expect(res.status).toBe(204);
        }
        const blocked = await POST(makeRequest({ kind: 'error', message: 'e11' }, ip));
        expect(blocked.status).toBe(429);
    });

    it('tells rate-limited senders when to retry', async () => {
        const ip = '198.51.100.98';
        for (let i = 0; i < 10; i++) {
            await POST(makeRequest({ kind: 'error', message: `e${i}` }, ip));
        }
        const blocked = await POST(makeRequest({ kind: 'error', message: 'last' }, ip));
        expect(blocked.status).toBe(429);
        expect(blocked.headers.get('Retry-After')).toBe('60');
    });
});
