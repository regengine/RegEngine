'use client';

import type { ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { Check } from 'lucide-react';

const STEPS = [
  { label: 'Profile', href: '/onboarding/setup/welcome', step: 1 },
  { label: 'Facility', href: '/onboarding/setup/facility', step: 2 },
  { label: 'FTL Check', href: '/onboarding/setup/ftl-check', step: 3 },
] as const;

function getActiveStep(pathname: string): number {
  if (pathname.includes('/ftl-check')) return 3;
  if (pathname.includes('/facility')) return 2;
  return 1;
}

export default function SetupLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const activeStep = getActiveStep(pathname);

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      {/* Progress stepper */}
      <nav className="mb-8" aria-label="Setup progress">
        <ol className="flex items-center justify-center gap-0">
          {STEPS.map((step, i) => {
            const isComplete = activeStep > step.step;
            const isCurrent = activeStep === step.step;

            return (
              <li key={step.step} className="flex items-center">
                {i > 0 && (
                  <div
                    className={`h-px w-10 sm:w-16 mx-1 transition-colors ${
                      isComplete ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-border)]'
                    }`}
                  />
                )}
                <div className="flex items-center gap-2">
                  <div
                    className={`flex h-8 w-8 items-center justify-center rounded-sm text-xs font-semibold transition-all ${
                      isComplete
                        ? 'bg-[var(--re-brand)] text-white'
                        : isCurrent
                          ? 'border-2 border-[var(--re-brand)] text-[var(--re-brand)]'
                          : 'border border-[var(--re-surface-border)] text-[var(--re-text-muted)]'
                    }`}
                  >
                    {isComplete ? <Check className="h-4 w-4" /> : step.step}
                  </div>
                  <span
                    className={`hidden sm:inline text-sm ${
                      isCurrent
                        ? 'font-medium text-[var(--re-text-primary)]'
                        : 'text-[var(--re-text-muted)]'
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Step content */}
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        {children}
      </motion.div>

      {/* Skip link */}
      <div className="mt-8 text-center">
        <button
          onClick={() => router.push('/dashboard')}
          className="text-xs text-[var(--re-text-muted)] hover:text-[var(--re-text-secondary)] transition-colors underline underline-offset-2"
        >
          Skip for now — I&apos;ll set up later
        </button>
      </div>
    </div>
  );
}
