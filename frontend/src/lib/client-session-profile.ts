import type { User } from '@/types/api';

// Held in memory only: never written to web storage (CodeQL
// js/clear-text-storage-of-sensitive-data). The real session fetch
// overwrites the placeholder profile below with the authenticated user.
let pendingSessionEmail: string | null = null;

export function getPendingSessionEmail(): string | null {
  return pendingSessionEmail;
}

export function seedClientSessionUser(email: string): void {
  if (typeof window === 'undefined') return;

  pendingSessionEmail = email;

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
