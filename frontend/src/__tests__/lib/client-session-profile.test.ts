import { beforeEach, describe, expect, it } from 'vitest';

import { seedClientSessionUser, serializeClientSessionUser } from '@/lib/client-session-profile';

function collectEmailValues(value: unknown, acc: unknown[] = []): unknown[] {
  if (Array.isArray(value)) {
    for (const item of value) collectEmailValues(item, acc);
  } else if (value !== null && typeof value === 'object') {
    for (const [key, entry] of Object.entries(value as Record<string, unknown>)) {
      if (key.toLowerCase() === 'email') acc.push(entry);
      collectEmailValues(entry, acc);
    }
  }
  return acc;
}

describe('seedClientSessionUser', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('stores a non-sensitive placeholder profile without the email', () => {
    const email = `${crypto.randomUUID()}@example.test`;

    seedClientSessionUser(email);

    const stored = window.localStorage.getItem('regengine_user');
    expect(stored).not.toBeNull();
    expect(stored as string).not.toContain(email);
    expect(stored as string).not.toContain(email.split('@')[0]);
    expect(window.sessionStorage.getItem('regengine_user')).toBeNull();

    const parsed = JSON.parse(stored as string) as Record<string, unknown>;
    expect(parsed).toMatchObject({
      id: 'email-session',
      email: '',
      is_sysadmin: false,
      status: 'active',
      role_name: 'member',
      permissions: [],
    });

    const emailValues = collectEmailValues(parsed);
    expect(emailValues.length).toBeGreaterThan(0);
    for (const value of emailValues) {
      expect(value).toBe('');
    }
  });
});

describe('serializeClientSessionUser', () => {
  it('omits email without mutating the authenticated profile or its permissions', () => {
    const user = {
      id: crypto.randomUUID(),
      email: `${crypto.randomUUID()}@example.test`,
      is_sysadmin: false,
      status: 'active',
      role_name: 'member',
      permissions: ['reports.read'],
    };
    const original = structuredClone(user);

    const stored = serializeClientSessionUser(user);

    expect(JSON.parse(stored)).toEqual({ ...original, email: '' });
    expect(stored).not.toContain(original.email);
    expect(stored).not.toContain(original.email.split('@')[0]);
    expect(user).toEqual(original);
  });
});
