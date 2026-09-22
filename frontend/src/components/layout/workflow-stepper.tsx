'use client';

import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Check } from 'lucide-react';

export type WorkflowStep = 'setup' | 'ingest' | 'review' | 'analyze';

interface WorkflowStepperProps {
  currentStep: WorkflowStep;
  completedSteps?: WorkflowStep[];
  className?: string;
}

const steps = [
  { id: 'setup' as const, label: 'Setup', href: '/onboarding', description: 'Configure credentials' },
  { id: 'ingest' as const, label: 'Ingest', href: '/ingest', description: 'Upload documents' },
  { id: 'review' as const, label: 'Review', href: '/review', description: 'Validate extractions' },
  { id: 'analyze' as const, label: 'Analyze', href: '/dashboard/compliance', description: 'Discover insights' },
];

/**
 * The one stepper recipe (SPEC §6 / proposal-A §6.6): 24px circle nodes
 * carrying a mono numeral, joined by hairlines. Current node is outlined in
 * ink, a completed node is filled ink with a Check, an upcoming node is
 * outlined in the default border. No brand fill, no 2px rings, no icon per
 * step — the numeral is the state, the label is the name.
 */
const nodeBase =
  'flex h-6 w-6 shrink-0 items-center justify-center rounded-full border font-mono text-label tracking-normal no-underline transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none';

/**
 * Zero-padded mono numerals ("01".."04"), matching the numbered mono labels the
 * redesign uses elsewhere. The padding is also load-bearing: a bare "3" in the
 * stepper collided with the "3" of an "Events detected" figure on /ingest
 * (src/__tests__/pages/ingest-handoff.test.tsx queries by exact text).
 */
function stepNumeral(index: number) {
  return String(index + 1).padStart(2, '0');
}

function nodeClasses(state: 'complete' | 'current' | 'pending') {
  return cn(
    nodeBase,
    state === 'complete' && 'border-re-text-primary bg-re-text-primary text-re-surface-card',
    state === 'current' && 'border-re-text-primary text-re-text-primary',
    state === 'pending' && 'border-re-border text-re-text-tertiary hover:border-re-border-strong',
  );
}

/**
 * `completedSteps` is authoritative whenever the caller supplies it: a step the
 * caller leaves out is NOT complete, even when it sits left of the current one.
 *
 * Position alone used to imply completion (`index < currentIndex`), which made
 * the prop dead on every current call site and put the stepper at odds with the
 * page around it -- /ingest rendered "01 Setup" as a filled check at the same
 * moment it rendered the "API Key Required" callout, and /review ignored
 * `isOnboarded` entirely. Both surfaces legitimately render a step the visitor
 * skipped, so the caller's answer wins.
 *
 * Callers that omit the prop keep the positional default.
 */
function isStepComplete(
  stepId: WorkflowStep,
  index: number,
  currentIndex: number,
  completedSteps: WorkflowStep[] | undefined,
): boolean {
  return completedSteps ? completedSteps.includes(stepId) : index < currentIndex;
}

export function WorkflowStepper({ currentStep, completedSteps, className }: WorkflowStepperProps) {
  const currentIndex = steps.findIndex(s => s.id === currentStep);

  return (
    <nav className={cn('w-full', className)} aria-label="Workflow progress">
      <ol className="flex items-start">
        {steps.map((step, index) => {
          const isComplete = isStepComplete(step.id, index, currentIndex, completedSteps);
          const isCurrent = step.id === currentStep;
          const state = isComplete ? 'complete' : isCurrent ? 'current' : 'pending';

          return (
            <li key={step.id} className={cn('flex items-start gap-2', index < steps.length - 1 && 'flex-1')}>
              <div className="flex min-w-0 flex-col items-center gap-2 text-center">
                <Link
                  href={step.href}
                  className={nodeClasses(state)}
                  aria-current={isCurrent ? 'step' : undefined}
                  aria-label={`Step ${index + 1}: ${step.label}`}
                >
                  {isComplete ? (
                    <Check className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
                  ) : (
                    stepNumeral(index)
                  )}
                </Link>
                <div className="min-w-0">
                  <p
                    className={cn(
                      'text-small font-medium',
                      isCurrent || isComplete ? 'text-re-text-primary' : 'text-re-text-tertiary',
                    )}
                  >
                    {step.label}
                  </p>
                  <p className="hidden text-small text-re-text-muted sm:block">{step.description}</p>
                </div>
              </div>
              {index < steps.length - 1 && (
                <div
                  className={cn(
                    'mt-3 h-px flex-1',
                    isComplete ? 'bg-re-text-primary' : 'bg-re-border',
                  )}
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// Minimal inline version for headers
export function WorkflowStepperInline({ currentStep, completedSteps }: WorkflowStepperProps) {
  const currentIndex = steps.findIndex(s => s.id === currentStep);

  return (
    <div className="flex items-center gap-1.5 text-small">
      {steps.map((step, index) => {
        const isComplete = isStepComplete(step.id, index, currentIndex, completedSteps);
        const isCurrent = step.id === currentStep;

        return (
          <div key={step.id} className="flex items-center gap-1.5">
            <Link
              href={step.href}
              aria-current={isCurrent ? 'step' : undefined}
              aria-label={`Step ${index + 1}: ${step.label}`}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-1 py-1 no-underline transition-colors duration-120 motion-reduce:transition-none',
                isCurrent ? 'text-re-text-primary' : 'text-re-text-tertiary hover:text-re-text-primary',
              )}
            >
              <span
                className={nodeClasses(isComplete ? 'complete' : isCurrent ? 'current' : 'pending')}
                aria-hidden="true"
              >
                {isComplete ? <Check className="h-3 w-3" strokeWidth={1.75} /> : stepNumeral(index)}
              </span>
              <span className="hidden font-medium md:inline">{step.label}</span>
            </Link>
            {index < steps.length - 1 && (
              <span className="h-px w-3 bg-re-border" aria-hidden="true" />
            )}
          </div>
        );
      })}
    </div>
  );
}
