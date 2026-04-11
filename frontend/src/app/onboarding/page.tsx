'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

/**
 * /onboarding — smart redirect to eliminate the waitlist dead-end.
 *
 * Authenticated users → onboarding setup flow
 * Unauthenticated users → signup page
 */
export default function OnboardingPage() {
  const router = useRouter();
  const { user, isHydrated } = useAuth();

  useEffect(() => {
    if (!isHydrated) return;
    if (user) {
      router.replace('/onboarding/setup/welcome');
    } else {
      router.replace('/signup');
    }
  }, [user, isHydrated, router]);

  return (
    <main className="min-h-[80vh] flex items-center justify-center">
      <div className="animate-pulse text-[var(--re-text-muted)] text-sm">
        Loading...
      </div>
    </main>
  );
}
