import { describe, expect, it } from 'vitest';
import { publicRequestErrorMessage, requestErrorStatus } from '@/lib/public-request-error';

const FALLBACK = 'Submission failed. Please try again.';
// Bodies below are the shapes services/shared/error_handling.py returns.
const httpError = (status: number, message: string, extra: Record<string, unknown> = {}) => ({
    status,
    data: { error: { type: `http_${status}`, message, ...extra } },
});

describe('publicRequestErrorMessage', () => {
    it('shows the server message from the error envelope on 4xx', () => {
        expect(publicRequestErrorMessage(httpError(404, 'Portal link not found or expired'), FALLBACK)).toBe(
            'Portal link not found or expired',
        );
        expect(
            publicRequestErrorMessage(httpError(429, 'Portal rate limit exceeded (20/60s for this link)'), FALLBACK),
        ).toBe('Portal rate limit exceeded (20/60s for this link)');
    });

    it('shows the failing field message for a validation error', () => {
        const error = {
            status: 422,
            data: {
                error: {
                    type: 'validation_error',
                    message: 'Request validation failed',
                    details: [
                        {
                            type: 'value_error',
                            loc: ['body', 'ship_date'],
                            msg: 'Value error, ship_date must be a calendar date in YYYY-MM-DD form',
                        },
                    ],
                },
            },
        };
        expect(publicRequestErrorMessage(error, FALLBACK)).toBe(
            'ship_date must be a calendar date in YYYY-MM-DD form',
        );
    });

    it('falls back when the server message says nothing', () => {
        expect(publicRequestErrorMessage(httpError(400, 'Invalid request'), FALLBACK)).toBe(FALLBACK);
        expect(
            publicRequestErrorMessage(
                { status: 422, data: { error: { type: 'validation_error', message: 'Request validation failed' } } },
                FALLBACK,
            ),
        ).toBe(FALLBACK);
    });

    it('never shows a 5xx message, but quotes the reference id when there is one', () => {
        expect(publicRequestErrorMessage(httpError(503, 'An internal error occurred'), FALLBACK)).toBe(FALLBACK);
        expect(publicRequestErrorMessage(httpError(500, 'db password is hunter2'), FALLBACK)).toBe(FALLBACK);
        expect(
            publicRequestErrorMessage(
                httpError(500, 'An internal error occurred', { correlation_id: 'abc-123', request_id: 'req-9' }),
                FALLBACK,
            ),
        ).toBe(`${FALLBACK} (Reference: abc-123)`);
    });

    it('gives a rate-limit sentence when a 429 has no usable message', () => {
        expect(publicRequestErrorMessage({ status: 429, data: null }, FALLBACK)).toBe(
            'Too many requests. Wait a minute and try again.',
        );
    });

    it('still reads the legacy { detail } shape', () => {
        expect(publicRequestErrorMessage({ status: 400, data: { detail: 'Bad GLN' } }, FALLBACK)).toBe('Bad GLN');
    });

    it('never shows machine codes or proxy text from a top-level string error', () => {
        // services/shared/tenant_rate_limiting.py (anonymous IP bucket)
        const ipLimited = {
            status: 429,
            data: { error: 'rate_limit_exceeded', detail: 'Limit of 100/min exceeded for anonymous' },
        };
        expect(publicRequestErrorMessage(ipLimited, FALLBACK)).toBe('Too many requests. Wait a minute and try again.');
        // The Next proxy's own refusals
        expect(publicRequestErrorMessage({ status: 403, data: { error: 'Missing CSRF token' } }, FALLBACK)).toBe(FALLBACK);
        expect(
            publicRequestErrorMessage({ status: 403, data: { error: 'Cross-origin mutation rejected' } }, FALLBACK),
        ).toBe(FALLBACK);
    });

    it('names the field for built-in validation messages', () => {
        const error = (loc: unknown[], msg: string) => ({
            status: 422,
            data: { error: { type: 'validation_error', message: 'Request validation failed', details: [{ loc, msg }] } },
        });
        expect(publicRequestErrorMessage(error(['body', 'ship_to_location'], 'Field required'), FALLBACK)).toBe(
            'Ship to location: Field required',
        );
        expect(publicRequestErrorMessage(error(['body', 'quantity'], 'Input should be greater than 0'), FALLBACK)).toBe(
            'Quantity: Input should be greater than 0',
        );
        expect(publicRequestErrorMessage(error(['body'], 'Field required'), FALLBACK)).toBe('Field required');
    });

    it('quotes the request id header when the proxy has replaced a 5xx body', () => {
        const error = { status: 502, data: { error: 'Upstream service unavailable' }, requestId: 'req-42' };
        expect(publicRequestErrorMessage(error, FALLBACK)).toBe(`${FALLBACK} (Reference: req-42)`);
        expect(publicRequestErrorMessage({ ...error, requestId: null }, FALLBACK)).toBe(FALLBACK);
    });

    it('falls back for network failures and unknown shapes', () => {
        expect(publicRequestErrorMessage(new TypeError('Failed to fetch'), FALLBACK)).toBe(FALLBACK);
        expect(publicRequestErrorMessage(undefined, FALLBACK)).toBe(FALLBACK);
        expect(publicRequestErrorMessage({ status: 404, data: '<html>Not Found</html>' }, FALLBACK)).toBe(FALLBACK);
        expect(publicRequestErrorMessage({ status: 400, data: { error: { message: 42 } } }, FALLBACK)).toBe(FALLBACK);
    });
});

describe('requestErrorStatus', () => {
    it('returns the numeric status only', () => {
        expect(requestErrorStatus({ status: 404, data: null })).toBe(404);
        expect(requestErrorStatus({ status: '404' })).toBeUndefined();
        expect(requestErrorStatus(new TypeError('Failed to fetch'))).toBeUndefined();
    });
});
