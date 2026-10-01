'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import {
  FileText,
  Search,
  ShieldCheck,
  Send,
  CheckCircle,
} from 'lucide-react';

export interface PhaseGate {
  label: string;
  targetHours: number;
  icon: React.ElementType;
}

const PHASES: PhaseGate[] = [
  { label: 'Request Received', targetHours: 0, icon: FileText },
  { label: 'Records Assembly', targetHours: 4, icon: Search },
  { label: 'Verification', targetHours: 6, icon: ShieldCheck },
  { label: 'Review & Submit', targetHours: 8, icon: Send },
  { label: 'Response Closed', targetHours: 24, icon: CheckCircle },
];

export function completedPhaseCount(milestones: string[], isComplete: boolean): number {
  const events = ['records_assembled', 'verified', 'reviewed', 'submitted'];
  let count = 1; // Request received is the only event proven by an SLA request.
  for (const event of events) {
    if (!milestones.includes(event)) break;
    if (event === 'submitted' && !isComplete) break;
    count++;
  }
  return count;
}

interface PhaseGatesProps {
  /** Seconds elapsed since the request was created */
  elapsedSeconds?: number;
  milestones?: string[];
  /** Whether the request has been completed */
  isComplete: boolean;
  className?: string;
}

export function PhaseGates({ milestones = [], isComplete, className }: PhaseGatesProps) {
  const activePhaseIndex = completedPhaseCount(milestones, isComplete);

  return (
    <div className={cn('w-full', className)}>
      <div className="flex items-center justify-between relative">
        {/* Connecting line */}
        <div className="absolute left-0 right-0 top-5 z-0 h-0.5 bg-re-border" />
        <motion.div
          className="absolute left-0 top-5 z-0 h-0.5 bg-re-brand"
          initial={{ width: '0%' }}
          animate={{ width: `${Math.min(100, (activePhaseIndex / (PHASES.length - 1)) * 100)}%` }}
          transition={{ duration: 0.5 }}
        />

        {PHASES.map((phase, idx) => {
          const isCompleted = idx === PHASES.length - 1 ? isComplete : idx < activePhaseIndex;
          const isCurrent = idx === activePhaseIndex && !isComplete;
          const Icon = phase.icon;

          return (
            <div key={phase.label} className="flex flex-col items-center z-10 relative">
              <div
                className={cn(
                  'flex h-10 w-10 items-center justify-center rounded-full border-2 transition-colors duration-120 motion-reduce:transition-none',
                  isCompleted && 'border-transparent bg-re-brand text-re-brand-foreground',
                  isCurrent && 'border-re-brand bg-re-surface-card text-re-brand',
                  !isCompleted && !isCurrent && 'border-re-border bg-re-surface-card text-re-text-tertiary',
                )}
              >
                {isCompleted ? (
                  <CheckCircle className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
                ) : (
                  <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                )}
              </div>
              <span className={cn(
                'mt-2 max-w-[80px] text-center text-small',
                isCompleted && 'font-medium text-re-text-primary',
                isCurrent && 'font-medium text-re-text-primary',
                !isCompleted && !isCurrent && 'text-re-text-tertiary',
              )}>
                {phase.label}
              </span>
              <span className="mt-0.5 text-label text-re-text-muted">
                {phase.targetHours === 0 ? 'Start' : `${phase.targetHours}h target`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
