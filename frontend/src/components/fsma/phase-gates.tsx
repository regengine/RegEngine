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
  { label: 'FDA Submission', targetHours: 24, icon: CheckCircle },
];

interface PhaseGatesProps {
  /** Seconds elapsed since the request was created */
  elapsedSeconds: number;
  /** Whether the request has been completed */
  isComplete: boolean;
  className?: string;
}

export function PhaseGates({ elapsedSeconds, isComplete, className }: PhaseGatesProps) {
  const elapsedHours = elapsedSeconds / 3600;

  // Determine the current active phase index
  let activePhaseIndex = 0;
  if (isComplete) {
    activePhaseIndex = PHASES.length; // All complete
  } else {
    for (let i = PHASES.length - 1; i >= 0; i--) {
      if (elapsedHours >= PHASES[i].targetHours) {
        activePhaseIndex = i + 1;
        break;
      }
    }
  }

  return (
    <div className={cn('w-full', className)}>
      <div className="flex items-center justify-between relative">
        {/* Connecting line */}
        <div className="absolute top-5 left-0 right-0 h-0.5 bg-muted z-0" />
        <motion.div
          className="absolute top-5 left-0 h-0.5 bg-[var(--re-brand)] z-0"
          initial={{ width: '0%' }}
          animate={{ width: `${Math.min(100, (activePhaseIndex / (PHASES.length - 1)) * 100)}%` }}
          transition={{ duration: 0.5 }}
        />

        {PHASES.map((phase, idx) => {
          const isCompleted = idx < activePhaseIndex;
          const isCurrent = idx === activePhaseIndex && !isComplete;
          const Icon = phase.icon;

          return (
            <div key={phase.label} className="flex flex-col items-center z-10 relative">
              <motion.div
                className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center border-2 transition-colors',
                  isCompleted && 'bg-[var(--re-brand)] border-[var(--re-brand)] text-white',
                  isCurrent && 'bg-white border-[var(--re-brand)] text-[var(--re-brand)]',
                  !isCompleted && !isCurrent && 'bg-[var(--re-surface-card)] border-muted text-muted-foreground',
                )}
                initial={{ scale: 0.8 }}
                animate={{ scale: isCurrent ? 1.1 : 1 }}
                transition={{ duration: 0.3 }}
              >
                {isCompleted ? (
                  <CheckCircle className="w-5 h-5" />
                ) : (
                  <Icon className="w-4 h-4" />
                )}
              </motion.div>
              <span className={cn(
                'text-xs mt-2 text-center max-w-[80px]',
                isCompleted && 'text-[var(--re-brand)] font-medium',
                isCurrent && 'text-foreground font-medium',
                !isCompleted && !isCurrent && 'text-muted-foreground',
              )}>
                {phase.label}
              </span>
              <span className="text-[10px] text-muted-foreground mt-0.5">
                {phase.targetHours === 0 ? 'Start' : `${phase.targetHours}h target`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
