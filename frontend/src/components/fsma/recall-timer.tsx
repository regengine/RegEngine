'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { RecallDrill, RecallStatus } from '@/types/fsma';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import {
  CheckCircle,
  PlayCircle,
  StopCircle,
  Bell,
  Timer,
} from 'lucide-react';

// Status configuration — every state travels as a StatusBadge (icon + label),
// so the drill's state survives greyscale and forced-colours mode.
const statusConfig: Record<RecallStatus, { label: string; state: ComplianceState }> = {
  PENDING: { label: 'Pending', state: 'pending' },
  IN_PROGRESS: { label: 'In Progress', state: 'in-progress' },
  MET: { label: 'SLA Met', state: 'compliant' },
  AT_RISK: { label: 'At Risk', state: 'at-risk' },
  BREACHED: { label: 'SLA Breached', state: 'non-compliant' },
  COMPLETED: { label: 'Completed', state: 'compliant' },
  CANCELLED: { label: 'Cancelled', state: 'unknown' },
};

// FDA 24-hour response objective in seconds
const SLA_SECONDS = 24 * 60 * 60; // 86400 seconds

interface RecallTimerProps {
  drill?: RecallDrill;
  onCancel?: () => void;
  onComplete?: () => void;
  onStartDrill?: () => void;
  className?: string;
}

export function RecallTimer({ drill, onCancel, onComplete, onStartDrill, className }: RecallTimerProps) {
  const [currentTime, setCurrentTime] = useState(() => Date.now());

  // Update timer every second
  useEffect(() => {
    if (!drill || drill.status === 'COMPLETED' || drill.status === 'CANCELLED') {
      return;
    }

    const interval = setInterval(() => {
      setCurrentTime(Date.now());
    }, 1000);

    return () => clearInterval(interval);
  }, [drill]);

  // Calculate remaining time
  const timeData = useMemo(() => {
    if (!drill) return null;

    const deadline = new Date(drill.deadline).getTime();
    const initiated = new Date(drill.initiated_at).getTime();
    const elapsed = Math.floor((currentTime - initiated) / 1000);
    const remaining = Math.max(0, Math.floor((deadline - currentTime) / 1000));
    const progress = Math.min(100, (elapsed / SLA_SECONDS) * 100);

    // Determine urgency level
    let urgency: 'normal' | 'warning' | 'critical' | 'breached' = 'normal';
    if (remaining <= 0) {
      urgency = 'breached';
    } else if (remaining <= 60 * 60) { // Less than 1 hour
      urgency = 'critical';
    } else if (remaining <= 4 * 60 * 60) { // Less than 4 hours
      urgency = 'warning';
    }

    return {
      elapsed,
      remaining,
      progress,
      urgency,
      deadline,
    };
  }, [drill, currentTime]);

  if (!drill) {
    return (
      <Card className={className}>
        <CardContent>
          <EmptyState
            bare
            icon={Timer}
            title="No active recall drill"
            action={
              <Button variant="secondary" onClick={onStartDrill} disabled={!onStartDrill}>
                <PlayCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Run Recall Drill
              </Button>
            }
          />
        </CardContent>
      </Card>
    );
  }

  const status = statusConfig[drill.status];

  return (
    <Card className={cn('relative overflow-hidden', className)}>
      <CardHeader className="flex-col items-stretch gap-1">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            FDA Recall Drill
          </CardTitle>
          <StatusBadge state={status.state} label={status.label} />
        </div>
        <CardDescription>
          24-Hour Response Objective Tracking
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Main Timer Display */}
        <div className="text-center">
          <CountdownDisplay
            seconds={timeData?.remaining || 0}
            urgency={timeData?.urgency || 'normal'}
            isActive={drill.status === 'IN_PROGRESS'}
          />
          <p className="mt-2 text-ui text-re-text-tertiary">
            Time Remaining for FDA 24-Hour Response Objective
          </p>
        </div>

        {/* Progress Bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-ui text-re-text-secondary">
            <span>Elapsed</span>
            <span className="font-mono tabular-nums text-re-text-primary">{formatDuration(timeData?.elapsed || 0)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-re-surface-inset">
            <motion.div
              className={cn(
                'h-full rounded-full',
                timeData?.urgency === 'breached' && 'bg-re-danger',
                timeData?.urgency === 'critical' && 'bg-re-danger',
                timeData?.urgency === 'warning' && 'bg-re-warning',
                timeData?.urgency === 'normal' && 'bg-re-success'
              )}
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, timeData?.progress || 0)}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
          <div className="flex justify-between text-label text-re-text-muted">
            <span>0h</span>
            <span>24h SLA</span>
          </div>
        </div>

        {/* Drill Details */}
        <div className="grid grid-cols-2 gap-4 border-t border-re-border-subtle pt-4">
          <div>
            <p className="text-label text-re-text-muted">Target Lot</p>
            <p className="mt-1 truncate font-mono text-[0.8125rem] text-re-text-primary">{drill.target_tlc}</p>
          </div>
          <div>
            <p className="text-label text-re-text-muted">Type</p>
            <p className="mt-1 text-ui font-medium text-re-text-primary">{drill.type}</p>
          </div>
          <div>
            <p className="text-label text-re-text-muted">Facilities Contacted</p>
            <p className="mt-1 text-ui font-medium tabular-nums text-re-text-primary">
              {drill.facilities_contacted} / {drill.total_facilities}
            </p>
          </div>
          <div>
            <p className="text-label text-re-text-muted">Lots Traced</p>
            <p className="mt-1 text-ui font-medium tabular-nums text-re-text-primary">{drill.lots_traced}</p>
          </div>
        </div>

        {/* Actions */}
        {drill.status === 'IN_PROGRESS' && (
          <div className="flex gap-2 border-t border-re-border-subtle pt-4">
            {onComplete && (
              <Button className="flex-1" onClick={onComplete}>
                <CheckCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Complete Drill
              </Button>
            )}
            {onCancel && (
              <Button variant="secondary" onClick={onCancel}>
                <StopCircle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                Cancel
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Large countdown display component
interface CountdownDisplayProps {
  seconds: number;
  urgency: 'normal' | 'warning' | 'critical' | 'breached';
  isActive: boolean;
}

function CountdownDisplay({ seconds, urgency, isActive }: CountdownDisplayProps) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  const colorClass = {
    normal: 'text-re-text-primary',
    warning: 'text-re-warning',
    critical: 'text-re-danger',
    breached: 'text-re-danger',
  }[urgency];

  return (
    <div className={cn('font-mono text-[3.5rem] font-semibold leading-none tabular-nums', colorClass)}>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={hours}
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
        >
          {String(hours).padStart(2, '0')}
        </motion.span>
      </AnimatePresence>
      <span className={cn(isActive && 'animate-pulse motion-reduce:animate-none')}>:</span>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={minutes}
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
        >
          {String(minutes).padStart(2, '0')}
        </motion.span>
      </AnimatePresence>
      <span className={cn(isActive && 'animate-pulse motion-reduce:animate-none')}>:</span>
      <AnimatePresence mode="popLayout">
        <motion.span
          key={secs}
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
        >
          {String(secs).padStart(2, '0')}
        </motion.span>
      </AnimatePresence>
    </div>
  );
}

// Mini recall status badge
interface RecallStatusBadgeProps {
  drill: RecallDrill;
  showTimer?: boolean;
  className?: string;
}

export function RecallStatusBadge({ drill, showTimer = true, className }: RecallStatusBadgeProps) {
  const [remaining, setRemaining] = useState(drill.remaining_seconds);
  const status = statusConfig[drill.status];

  useEffect(() => {
    if (drill.status !== 'IN_PROGRESS') return;

    const interval = setInterval(() => {
      setRemaining(r => Math.max(0, r - 1));
    }, 1000);

    return () => clearInterval(interval);
  }, [drill.status]);

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <StatusBadge state={status.state} label={status.label} />
      {showTimer && drill.status === 'IN_PROGRESS' && (
        <span className={cn(
          'font-mono text-[0.8125rem] tabular-nums',
          remaining <= 3600 ? 'text-re-danger' : 'text-re-text-tertiary'
        )}>
          {formatDuration(remaining)}
        </span>
      )}
    </div>
  );
}

// SLA Gauge component
interface SLAGaugeProps {
  percentage: number;
  className?: string;
}

export function SLAGauge({ percentage, className }: SLAGaugeProps) {
  const circumference = 2 * Math.PI * 45; // radius = 45
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  const color = percentage >= 90 ? 'stroke-re-success' : percentage >= 70 ? 'stroke-re-warning' : 'stroke-re-danger';

  return (
    <div className={cn('relative w-32 h-32', className)}>
      <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
        {/* Background circle */}
        <circle
          cx="50"
          cy="50"
          r="45"
          fill="none"
          stroke="currentColor"
          strokeWidth="8"
          className="text-re-border-subtle"
        />
        {/* Progress circle */}
        <motion.circle
          cx="50"
          cy="50"
          r="45"
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          className={color}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1 }}
          style={{ strokeDasharray: circumference }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-title tabular-nums text-re-text-primary">{Math.round(percentage)}%</span>
        <span className="text-label text-re-text-muted">SLA Met</span>
      </div>
    </div>
  );
}

// Helper function to format duration
function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;

  if (h > 0) {
    return `${h}h ${m}m ${s}s`;
  } else if (m > 0) {
    return `${m}m ${s}s`;
  } else {
    return `${s}s`;
  }
}
