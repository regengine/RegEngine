import { describe, expect, it } from 'vitest';
import { withCsrfHeaders } from '@/lib/fetch-with-csrf';

describe('withCsrfHeaders', () => {
    it('adds the CSRF token to mutating requests', () => {
        document.cookie = 're_csrf=test-token';

        const options = withCsrfHeaders({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const headers = new Headers(options.headers);

        expect(headers.get('x-csrf-token')).toBe('test-token');
        expect(headers.get('content-type')).toBe('application/json');
    });

    it('leaves GET requests unchanged', () => {
        const options = { method: 'GET', headers: { Accept: 'application/json' } };

        expect(withCsrfHeaders(options)).toBe(options);
    });
});
