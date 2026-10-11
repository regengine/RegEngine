import { describe, expect, it } from 'vitest';
import { apiError, getErrorStatus, isAuthError } from '@/lib/api-error';

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

    it('flags only 401 and 403 as auth errors', () => {
        expect(isAuthError(apiError(401, ''))).toBe(true);
        expect(isAuthError(apiError(403, ''))).toBe(true);
        expect(isAuthError(apiError(404, ''))).toBe(false);
        expect(isAuthError(apiError(500, ''))).toBe(false);
        expect(isAuthError(new Error('network down'))).toBe(false);
    });
});
