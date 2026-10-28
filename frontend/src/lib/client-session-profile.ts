import type { User } from '@/types/api';

/**
 * Client-side cache of the signed-in user's profile.
 *
 * The profile is kept in sessionStorage (tab-scoped, gone when the tab
 * closes) instead of localStorage, so it is not left behind across browser
 * restarts or after logout. Only the fields the UI needs for rendering and
 * role checks are stored; the server session (/api/session) stays the
 * source of truth and refreshes this cache on hydration.
 */
export const CLIENT_SESSION_USER_KEY = 'regengine_user';

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function getLocalStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Reduce a user to the fields the client actually reads. */
export function toClientSessionProfile(user: User): User {
  const profile: User = {
    id: user.id,
    email: user.email,
    is_sysadmin: user.is_sysadmin === true,
    status: user.status,
  };
  if (user.role_id !== undefined) profile.role_id = user.role_id;
  if (user.role_name !== undefined) profile.role_name = user.role_name;
  if (user.organization_id !== undefined) profile.organization_id = user.organization_id;
  if (user.auth_method !== undefined) profile.auth_method = user.auth_method;
  if (Array.isArray(user.permissions)) profile.permissions = [...user.permissions];
  return profile;
}

/** Remove the copy that older builds persisted in localStorage. */
export function purgeLegacyClientSessionUser(): void {
  getLocalStorage()?.removeItem(CLIENT_SESSION_USER_KEY);
}

export function writeClientSessionUser(user: User | null | undefined): void {
  const storage = getSessionStorage();
  if (!storage) return;
  if (!user) {
    storage.removeItem(CLIENT_SESSION_USER_KEY);
    return;
  }
  storage.setItem(CLIENT_SESSION_USER_KEY, JSON.stringify(toClientSessionProfile(user)));
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || typeof value === 'string';
}

function isOptionalStringOrNull(value: unknown): boolean {
  return value === undefined || value === null || typeof value === 'string';
}

function isValidCachedUser(parsed: unknown): parsed is Partial<User> {
  if (!parsed || typeof parsed !== 'object') return false;
  const value = parsed as Record<string, unknown>;
  if (typeof value.id !== 'string' || typeof value.email !== 'string') return false;
  if (value.is_sysadmin !== undefined && typeof value.is_sysadmin !== 'boolean') return false;
  if (value.status !== undefined && typeof value.status !== 'string') return false;
  if (!isOptionalString(value.role_id)) return false;
  if (!isOptionalString(value.role_name)) return false;
  if (!isOptionalStringOrNull(value.organization_id)) return false;
  if (!isOptionalStringOrNull(value.auth_method)) return false;
  if (
    value.permissions !== undefined &&
    !(Array.isArray(value.permissions) && value.permissions.every((p) => typeof p === 'string'))
  ) {
    return false;
  }
  return true;
}

export function readClientSessionUser(): User | null {
  const raw = getSessionStorage()?.getItem(CLIENT_SESSION_USER_KEY);
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!isValidCachedUser(parsed)) {
      return null;
    }
    return toClientSessionProfile(parsed as User);
  } catch {
    return null;
  }
}

/** Clear every client copy of the profile (call on logout). */
export function clearClientSessionUser(): void {
  getSessionStorage()?.removeItem(CLIENT_SESSION_USER_KEY);
  purgeLegacyClientSessionUser();
}

export function seedClientSessionUser(email: string): void {
  if (typeof window === 'undefined') return;

  writeClientSessionUser({
    id: 'email-session',
    email,
    is_sysadmin: false,
    status: 'active',
    role_name: 'member',
    permissions: [],
  });
  purgeLegacyClientSessionUser();
}
