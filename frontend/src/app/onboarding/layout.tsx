'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';

import { useAuth } from '@/lib/auth-context';
import { Container } from '@/components/layout/container';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';

const navLinkClasses =
  'text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none';

export default function OnboardingLayout({ children }: { children: ReactNode }) {
  const { user } = useAuth();

  return (
    <div className="min-h-screen bg-re-surface-base text-re-text-primary">
      <header className="sticky top-0 z-40 h-14 border-b border-re-border-subtle bg-re-surface-base">
        <Container width="marketing" className="flex h-full items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 no-underline">
            <span className="hidden md:inline-flex">
              <RegEngineWordmark size="sm" />
            </span>
            <span className="inline-flex md:hidden">
              <RegEngineWordmark size="sm" showText={false} />
            </span>
          </Link>

          <div className="flex items-center gap-5">
            {user ? (
              <Link href="/dashboard" className={navLinkClasses}>
                Dashboard
              </Link>
            ) : (
              <Link href="/login" className={navLinkClasses}>
                Log In
              </Link>
            )}
            <Link href="/" className={navLinkClasses}>
              <span className="hidden md:inline">Back to Site</span>
              <span className="md:hidden">Exit</span>
            </Link>
          </div>
        </Container>
      </header>

      {children}
    </div>
  );
}
