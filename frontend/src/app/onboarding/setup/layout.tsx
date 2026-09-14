'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import { Check } from 'lucide-react';

import { cn } from '@/lib/utils';

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
  const activeStep = getActiveStep(pathname);

  return (
    <div className="mx-auto w-full max-w-[640px] px-5 py-10 sm:px-8">
      {/* Progress stepper — the one recipe: 24px circle, mono numeral, hairline. */}
      <nav className="mb-8" aria-label="Setup progress">
        <ol className="flex items-center justify-center">
          {STEPS.map((step, i) => {
            const isComplete = activeStep > step.step;
            const isCurrent = activeStep === step.step;

            return (
              <li key={step.step} className="flex items-center">
                {i > 0 && (
                  <div
                    className={cn(
                      'mx-3 h-px w-10 transition-colors duration-120 motion-reduce:transition-none sm:w-16',
                      isComplete ? 'bg-re-text-primary' : 'bg-re-border',
                    )}
                  />
                )}
                <div className="flex items-center gap-2">
                  <span
                    aria-current={isCurrent ? 'step' : undefined}
                    className={cn(
                      'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border font-mono text-label transition-colors duration-120 motion-reduce:transition-none',
                      isComplete && 'border-re-text-primary bg-re-text-primary text-re-surface-card',
                      isCurrent && 'border-re-text-primary text-re-text-primary',
                      !isComplete && !isCurrent && 'border-re-border text-re-text-tertiary',
                    )}
                  >
                    {isComplete ? (
                      <Check className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
                    ) : (
                      String(step.step).padStart(2, '0')
                    )}
                  </span>
                  <span
                    className={cn(
                      'hidden text-small sm:inline',
                      isCurrent ? 'font-medium text-re-text-primary' : 'text-re-text-tertiary',
                    )}
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
    </div>
  );
}
