'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import Image from 'next/image';

import { useAuth } from '@/lib/auth-context';

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
            <Image
              src="/logo-dark.png"
              alt="RegEngine"
              width={120}
              height={28}
              className="hidden md:block"
              style={{ objectFit: 'contain' }}
              priority
            />
            <Image
              src="/logo-dark.png"
              alt="RegEngine"
              width={32}
              height={32}
              className="md:hidden"
              style={{ objectFit: 'contain' }}
              priority
            />
            <span className="ml-0.5 text-[9px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded-full">
              Beta
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
