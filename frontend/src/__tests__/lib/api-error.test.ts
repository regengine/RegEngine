import { describe, expect, it } from 'vitest';
import { apiError, getErrorRequestId, getErrorStatus, isAuthError, requestIdFromResponse, withRequestId } from '@/lib/api-error';

describe('api-error helpers', () => {
    it('builds errors with machine-readable status in both fields', () => {
        const err = apiError(401, 'Unauthorized');
        expect(err.message).toContain('401');
        expect(err.status).toBe(401);
        expect(err.response?.status).toBe(401);
    });

    it('reads status from either the direct or the nested response shape', () => {
        expect(getErrorStatus(apiError(403, 'Forbidden'))).toBe(403);
        expect(getErrorStatus({ response: { status: 401 } })).toBe(401);
        expect(getErrorStatus(new Error('plain'))).toBeNull();
        expect(getErrorStatus(null)).toBeNull();
        expect(getErrorStatus({ status: '401' })).toBeNull();
    });

    it('attaches a request ID to the direct and nested error shape', () => {
        const requestId = crypto.randomUUID();
        const err = apiError(500, 'Internal Server Error', requestId);
        expect(err.requestId).toBe(requestId);
        expect(err.response?.requestId).toBe(requestId);
        expect(getErrorRequestId(err)).toBe(requestId);
        expect(getErrorRequestId(apiError(500, ''))).toBeUndefined();
    });

    it('reads the request ID from the failed response header', () => {
        const requestId = crypto.randomUUID();
        const plainRequestId = crypto.randomUUID();
        const res = new Response('boom', { status: 500, headers: { 'x-request-id': requestId } });
        expect(requestIdFromResponse(res)).toBe(requestId);
        expect(requestIdFromResponse(new Response('boom', { status: 500 }))).toBeUndefined();
        expect(requestIdFromResponse(null)).toBeUndefined();
        expect(requestIdFromResponse({ ok: false, status: 500 })).toBeUndefined();
        expect(requestIdFromResponse({ headers: { 'x-request-id': plainRequestId } })).toBe(plainRequestId);

        const err = withRequestId(new Error('nope'), res);
        expect(err.message).toBe('nope');
        expect(getErrorRequestId(err)).toBe(requestId);
    });

    it('reads the request ID from API client header and plain shapes', () => {
        const headerRequestId = crypto.randomUUID();
        const directRequestId = crypto.randomUUID();
        expect(getErrorRequestId({ response: { status: 500, headers: { 'x-request-id': headerRequestId } } })).toBe(headerRequestId);
        expect(getErrorRequestId({ requestId: directRequestId })).toBe(directRequestId);
        expect(getErrorRequestId(new Error('plain'))).toBeUndefined();
        expect(getErrorRequestId(null)).toBeUndefined();
        expect(getErrorRequestId({ requestId: 42 })).toBeUndefined();
    });

    it('flags only 401 and 403 as auth errors', () => {
        expect(isAuthError(apiError(401, ''))).toBe(true);
        expect(isAuthError(apiError(403, ''))).toBe(true);
        expect(isAuthError(apiError(404, ''))).toBe(false);
        expect(isAuthError(apiError(500, ''))).toBe(false);
        expect(isAuthError(new Error('network down'))).toBe(false);
    });
});
