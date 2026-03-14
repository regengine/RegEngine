'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';

import { useAuth } from '@/lib/auth-context';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';

export default function OnboardingLayout({ children }: { children: ReactNode }) {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
      <header className="h-12 sticky top-0 z-40 border-b border-[var(--re-nav-border)] backdrop-blur-[16px] bg-[var(--re-nav-bg)]">
        <div className="max-w-[1120px] mx-auto h-full px-6 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 no-underline">
            <span className="hidden md:inline-flex">
              <RegEngineWordmark size="sm" />
            </span>
            <span className="md:hidden inline-flex">
              <RegEngineWordmark size="sm" showText={false} />
            </span>
          </Link>

          <div className="flex items-center gap-4 text-[13px]">
            {user ? (
              <Link href="/dashboard" className="text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] no-underline transition-colors">
                Dashboard
              </Link>
            ) : (
              <Link href="/login" className="text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] no-underline transition-colors">
                Log In
              </Link>
            )}
            <Link href="/" className="text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] no-underline transition-colors">
              <span className="hidden md:inline">Back to Site</span>
              <span className="md:hidden">Exit</span>
            </Link>
          </div>
        </div>
      </header>

      {children}
    </div>
  );
}
