/**
 * #2885 — developer playground POSTs must carry the CSRF header.
 *
 * sendRequest() built its headers with only X-RegEngine-API-Key and called raw
 * global fetch(). Every playground POST goes to a same-origin BFF path
 * (/api/ingestion/api/v1/...), so src/proxy.ts applies the double-submit CSRF
 * check and returned 403 "Missing CSRF token" before the proxy ever ran:
 *
 *   - The exemption list in src/lib/csrf.ts contains '/api/v1/webhooks/', which
 *     is the next.config.js rewrite source. It does NOT prefix-match the
 *     proxied '/api/ingestion/api/v1/webhooks/ingest' this page actually calls.
 *   - The other two POST endpoints (/api/ingestion/api/v1/chain/verify-all and
 *     /api/ingestion/api/v1/portal/links) are not exempt under any spelling.
 *   - The Bearer bypass in src/proxy.ts cannot apply: it requires an
 *     `Authorization: Bearer` header AND no Origin/Referer, but this page sends
 *     an API-key header and a browser always attaches Origin/Referer.
 *
 * The fix is to send the token via fetchWithCsrf, NOT to widen the exempt list.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import APIPlayground from '@/app/developer/portal/playground/page';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: unknown[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

const rawFetch = vi.fn();

beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ isAuthenticated: true });
    vi.stubGlobal('fetch', rawFetch);
    fetchWithCsrfMock.mockResolvedValue({
        status: 200,
        statusText: 'OK',
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ success: true }),
        text: async () => '{"success":true}',
    });
});

describe('developer playground CSRF (#2885)', () => {
    it('sends the default POST endpoint through fetchWithCsrf, not raw fetch', async () => {
        const user = userEvent.setup();
        render(<APIPlayground />);

        // ENDPOINTS[0] is the webhook ingest POST, selected by default, and an
        // authenticated user starts in live (non-demo) mode.
        await user.click(screen.getByRole('button', { name: 'Send Request' }));

        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalled());

        const [url, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(url).toBe('/api/ingestion/api/v1/webhooks/ingest');
        expect(init.method).toBe('POST');

        // Raw fetch would skip withCsrfHeaders() and get a 403 from the proxy.
        expect(rawFetch).not.toHaveBeenCalled();
    });

    it('still passes the API key and content type through', async () => {
        const user = userEvent.setup();
        render(<APIPlayground />);

        await user.click(screen.getByRole('button', { name: 'Send Request' }));
        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalled());

        const [, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        const headers = new Headers(init.headers);
        expect(headers.get('X-RegEngine-API-Key')).toBeTruthy();
        expect(headers.get('Content-Type')).toBe('application/json');
    });
});
