/**
 * /api/contact rejects over-long emails before EMAIL_RE runs
 * (code-scanning js/polynomial-redos alert 61).
 */
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { POST } from '@/app/api/contact/route';

let ipCounter = 0;

function post(email: string): Promise<Response> {
    ipCounter += 1;
    return POST(
        new Request('http://localhost/api/contact', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-forwarded-for': `198.51.100.${ipCounter}`,
            },
            body: JSON.stringify({ name: 'x', email, message: 'x' }),
        }),
    );
}

// Builds an address of exactly `length` characters in code.
function emailOfLength(length: number): string {
    const domain = '@example.com';
    return 'a'.repeat(length - domain.length) + domain;
}

describe('POST /api/contact email length cap', () => {
    beforeEach(() => {
        process.env.CONTACT_WEBHOOK_URL = 'https://contact-provider.example/submit';
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    });

    afterEach(() => {
        delete process.env.CONTACT_WEBHOOK_URL;
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    });

    it('accepts a 254-character email', async () => {
        const res = await post(emailOfLength(254));
        expect(res.status).toBe(200);
    });

    it('rejects a 255-character email as invalid_email', async () => {
        const res = await post(emailOfLength(255));
        expect(res.status).toBe(400);
        expect((await res.json()).error).toBe('invalid_email');
    });

    it('rejects a very long email before regex validation', async () => {
        const email = 'a@' + 'a.'.repeat(50_000) + '@';
        const originalTest = RegExp.prototype.test;
        const regexTest = vi.spyOn(RegExp.prototype, 'test').mockImplementation(function (this: RegExp, value: string) {
            // A missing length guard must fail this test without running the expensive regex.
            return value === email ? false : originalTest.call(this, value);
        });

        const res = await post(email);
        expect(res.status).toBe(400);
        expect((await res.json()).error).toBe('invalid_email');
        expect(regexTest).not.toHaveBeenCalledWith(email);
        expect(fetch).not.toHaveBeenCalled();
    });
});
