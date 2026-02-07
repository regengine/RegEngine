'use client';

import Link from 'next/link';
import { cn } from '@/lib/utils';
import { Settings, Upload, CheckSquare, BarChart3, Check } from 'lucide-react';

export type WorkflowStep = 'setup' | 'ingest' | 'review' | 'analyze';

interface WorkflowStepperProps {
  currentStep: WorkflowStep;
  completedSteps?: WorkflowStep[];
  className?: string;
}

const steps = [
  { id: 'setup' as const, label: 'Setup', href: '/onboarding', icon: Settings, description: 'Configure credentials' },
  { id: 'ingest' as const, label: 'Ingest', href: '/ingest', icon: Upload, description: 'Upload documents' },
  { id: 'review' as const, label: 'Review', href: '/review', icon: CheckSquare, description: 'Validate extractions' },
  { id: 'analyze' as const, label: 'Analyze', href: '/opportunities', icon: BarChart3, description: 'Discover insights' },
];

export function WorkflowStepper({ currentStep, completedSteps = [], className }: WorkflowStepperProps) {
  const currentIndex = steps.findIndex(s => s.id === currentStep);

  return (
    <nav className={cn('w-full', className)} aria-label="Workflow progress">
      <ol className="flex flex-col md:flex-row md:items-center justify-between gap-4 md:gap-0">
        {steps.map((step, index) => {
          const isComplete = completedSteps.includes(step.id) || index < currentIndex;
          const isCurrent = step.id === currentStep;
          const isPending = index > currentIndex && !completedSteps.includes(step.id);

          return (
            <li key={step.id} className="flex-1 relative">
              <div className="flex flex-col items-center">
                {/* Connector line */}
                {index > 0 && (
                  <>
                    {/* Desktop Horizontal Line */}
                    <div
                      className={cn(
                        'hidden md:block absolute top-5 right-1/2 w-full h-0.5 -translate-y-1/2',
                        isComplete || isCurrent ? 'bg-primary' : 'bg-muted'
                      )}
                      style={{ width: 'calc(100% - 2.5rem)', right: 'calc(50% + 1.25rem)' }}
                    />
                    {/* Mobile Vertical Line */}
                    <div
                      className={cn(
                        'md:hidden absolute -top-4 left-1/2 h-4 w-0.5 -translate-x-1/2',
                        isComplete || isCurrent ? 'bg-primary' : 'bg-muted'
                      )}
                    />
                  </>
                )}

                {/* Step circle */}
                <Link
                  href={step.href}
                  className={cn(
                    'relative z-10 flex items-center justify-center w-10 h-10 rounded-full border-2 transition-all',
                    isComplete && 'bg-primary border-primary text-primary-foreground',
                    isCurrent && 'border-primary bg-primary/10 text-primary',
                    isPending && 'border-muted bg-background text-muted-foreground'
                  )}
                >
                  {isComplete ? (
                    <Check className="w-5 h-5" />
                  ) : (
                    <step.icon className="w-5 h-5" />
                  )}
                </Link>

                {/* Label */}
                <div className="mt-2 text-center">
                  <p
                    className={cn(
                      'text-sm font-medium',
                      isCurrent && 'text-primary',
                      isPending && 'text-muted-foreground'
                    )}
                  >
                    {step.label}
                  </p>
                  <p className="text-xs text-muted-foreground hidden sm:block">
                    {step.description}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// Minimal inline version for headers
export function WorkflowStepperInline({ currentStep, completedSteps = [] }: WorkflowStepperProps) {
  const currentIndex = steps.findIndex(s => s.id === currentStep);

  return (
    <div className="flex items-center gap-1 text-sm">
      {steps.map((step, index) => {
        const isComplete = completedSteps.includes(step.id) || index < currentIndex;
        const isCurrent = step.id === currentStep;

        return (
          <div key={step.id} className="flex items-center">
            <Link
              href={step.href}
              className={cn(
                'flex items-center gap-1 px-2 py-1 rounded-md transition-colors',
                isComplete && 'text-primary',
                isCurrent && 'bg-primary/10 text-primary font-medium',
                !isComplete && !isCurrent && 'text-muted-foreground hover:text-foreground'
              )}
            >
              {isComplete ? (
                <Check className="w-3 h-3" />
              ) : (
                <step.icon className="w-3 h-3" />
              )}
              <span className="hidden md:inline">{step.label}</span>
            </Link>
            {index < steps.length - 1 && (
              <span className="text-muted-foreground mx-1">/</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
