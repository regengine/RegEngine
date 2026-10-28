import type { User } from '@/types/api';

// Keep the authenticated profile intact in memory; cache no email in web storage.
export function serializeClientSessionUser(user: User | null): string {
  return JSON.stringify(user ? { ...user, email: '' } : null);
}

// Seeds a non-sensitive placeholder profile only: the email argument is
// intentionally never persisted to web storage nor held in module state
// (CodeQL js/clear-text-storage-of-sensitive-data). The real session fetch
// provides the authenticated user in memory.
export function seedClientSessionUser(email: string): void {
  void email;
  if (typeof window === 'undefined') return;

  const user: User = {
    id: 'email-session',
    email: '',
    is_sysadmin: false,
    status: 'active',
    role_name: 'member',
    permissions: [],
  };

  window.localStorage.setItem('regengine_user', serializeClientSessionUser(user));
}
