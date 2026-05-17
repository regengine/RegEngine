import { describe, expect, it } from 'vitest';
import { NextRequest } from 'next/server';
import {
    buildAdminProxyHeaders,
    isUnauthenticatedAdminPath,
} from '@/app/api/admin/[...path]/route';

describe('admin proxy unauthenticated auth paths', () => {
    it('allows password-reset paths through before a RegEngine session exists', () => {
        expect(isUnauthenticatedAdminPath('auth/forgot-password')).toBe(true);
        expect(isUnauthenticatedAdminPath('auth/reset-password')).toBe(true);
        expect(isUnauthenticatedAdminPath('auth/email-code/request')).toBe(true);
        expect(isUnauthenticatedAdminPath('auth/email-code/confirm')).toBe(true);
    });

    it('preserves a Supabase recovery Authorization header over stale cookies', () => {
        const request = new NextRequest('http://localhost/api/admin/auth/reset-password', {
            method: 'POST',
            headers: {
                authorization: 'Bearer supabase-recovery-token',
                cookie: 're_access_token=stale-regengine-token',
            },
        });

        const headers = buildAdminProxyHeaders(request);

        expect(headers.get('authorization')).toBe('Bearer supabase-recovery-token');
    });
});
