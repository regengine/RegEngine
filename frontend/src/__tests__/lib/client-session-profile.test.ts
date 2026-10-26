import { describe, it, expect, beforeEach } from 'vitest';
import {
    CLIENT_SESSION_USER_KEY,
    clearClientSessionUser,
    purgeLegacyClientSessionUser,
    readClientSessionUser,
    seedClientSessionUser,
    toClientSessionProfile,
    writeClientSessionUser,
} from '@/lib/client-session-profile';
import type { User } from '@/types/api';

describe('client-session-profile', () => {
    beforeEach(() => {
        window.sessionStorage.clear();
        window.localStorage.clear();
    });

    it('seeds the profile into sessionStorage, never localStorage', () => {
        seedClientSessionUser('seed@regengine.co');

        expect(window.localStorage.getItem(CLIENT_SESSION_USER_KEY)).toBeNull();
        expect(readClientSessionUser()).toEqual({
            id: 'email-session',
            email: 'seed@regengine.co',
            is_sysadmin: false,
            status: 'active',
            role_name: 'member',
            permissions: [],
        });
    });

    it('removes a legacy localStorage copy when seeding', () => {
        window.localStorage.setItem(CLIENT_SESSION_USER_KEY, '{"id":"old","email":"old@regengine.co"}');
        seedClientSessionUser('seed@regengine.co');
        expect(window.localStorage.getItem(CLIENT_SESSION_USER_KEY)).toBeNull();
    });

    it('stores only the fields the client needs', () => {
        const user = {
            id: crypto.randomUUID(),
            email: 'member@regengine.co',
            is_sysadmin: false,
            status: 'active',
            role_name: 'member',
            permissions: ['reports.read'],
            created_at: '2026-10-26T00:00:00Z',
            name: 'Extra Field',
            tenant_id: crypto.randomUUID(),
        } as unknown as User;

        writeClientSessionUser(user);
        const stored = JSON.parse(window.sessionStorage.getItem(CLIENT_SESSION_USER_KEY) as string);

        expect(Object.keys(stored).sort()).toEqual(
            ['email', 'id', 'is_sysadmin', 'permissions', 'role_name', 'status'],
        );
        expect(toClientSessionProfile(user)).toEqual(stored);
    });

    it('clears both the session copy and any legacy localStorage copy', () => {
        seedClientSessionUser('seed@regengine.co');
        window.localStorage.setItem(CLIENT_SESSION_USER_KEY, '{}');

        clearClientSessionUser();

        expect(window.sessionStorage.getItem(CLIENT_SESSION_USER_KEY)).toBeNull();
        expect(window.localStorage.getItem(CLIENT_SESSION_USER_KEY)).toBeNull();
        expect(readClientSessionUser()).toBeNull();
    });

    it('purgeLegacyClientSessionUser leaves the sessionStorage copy alone', () => {
        seedClientSessionUser('seed@regengine.co');
        window.localStorage.setItem(CLIENT_SESSION_USER_KEY, '{}');

        purgeLegacyClientSessionUser();

        expect(window.localStorage.getItem(CLIENT_SESSION_USER_KEY)).toBeNull();
        expect(readClientSessionUser()?.email).toBe('seed@regengine.co');
    });

    it('ignores corrupt or incomplete stored data', () => {
        window.sessionStorage.setItem(CLIENT_SESSION_USER_KEY, 'not-json');
        expect(readClientSessionUser()).toBeNull();
        window.sessionStorage.setItem(CLIENT_SESSION_USER_KEY, '{"email":"x@regengine.co"}');
        expect(readClientSessionUser()).toBeNull();
    });
});
