import type { User } from '@/types/api';

// Seeds a non-sensitive placeholder profile only: the email argument is
// intentionally never persisted to web storage nor held in module state
// (CodeQL js/clear-text-storage-of-sensitive-data). The real session fetch
// overwrites the placeholder profile below with the authenticated user.
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

  window.localStorage.setItem('regengine_user', JSON.stringify(user));
}
