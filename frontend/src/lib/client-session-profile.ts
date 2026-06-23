import type { User } from '@/types/api';

export function seedClientSessionUser(email: string): void {
  if (typeof window === 'undefined') return;

  const user: User = {
    id: 'email-session',
    email,
    is_sysadmin: false,
    status: 'active',
    role_name: 'member',
    permissions: [],
  };

  window.localStorage.setItem('regengine_user', JSON.stringify(user));
}
