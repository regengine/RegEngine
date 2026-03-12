'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';

import { useAuth } from '@/lib/auth-context';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';

export default function OnboardingLayout({ children }: { children: ReactNode }) {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
      <header
        style={{
          height: '48px',
          position: 'sticky',
          top: 0,
          zIndex: 40,
          borderBottom: '1px solid rgba(255,255,255,0.04)',
          backdropFilter: 'blur(16px)',
          background: 'rgba(6,9,15,0.85)',
        }}
      >
        <div
          style={{
            maxWidth: '1120px',
            margin: '0 auto',
            height: '100%',
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
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
              <Link href="/dashboard" className="text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] no-underline">
                Dashboard
              </Link>
            ) : (
              <Link href="/login" className="text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] no-underline">
                Log In
              </Link>
            )}
            <Link href="/" className="text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] no-underline">
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
