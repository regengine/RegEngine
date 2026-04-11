'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { RecallDrill, RecallStatus } from '@/types/fsma';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  AlertTriangle,
  Clock,
  CheckCircle,
  XCircle,
  PlayCircle,
  StopCircle,
  RefreshCw,
  Bell,
  Timer,
} from 'lucide-react';

// Status configuration
const statusConfig: Record<RecallStatus, {
  label: string;
  color: string;
  bgColor: string;
  icon: React.ElementType;
}> = {
  PENDING: { label: 'Pending', color: 'text-re-text-disabled', bgColor: 'bg-re-surface-elevated', icon: Clock },
  IN_PROGRESS: { label: 'In Progress', color: 'text-re-info', bgColor: 'bg-re-info-muted', icon: RefreshCw },
  MET: { label: 'SLA Met', color: 'text-re-success', bgColor: 'bg-re-success-muted', icon: CheckCircle },
  AT_RISK: { label: 'At Risk', color: 'text-re-warning', bgColor: 'bg-re-warning-muted', icon: AlertTriangle },
  BREACHED: { label: 'SLA Breached', color: 'text-re-danger', bgColor: 'bg-re-danger-muted', icon: XCircle },
  COMPLETED: { label: 'Completed', color: 'text-re-success', bgColor: 'bg-re-success-muted', icon: CheckCircle },
  CANCELLED: { label: 'Cancelled', color: 'text-re-text-disabled', bgColor: 'bg-re-surface-elevated', icon: StopCircle },
};

// FDA 24-hour SLA in seconds
const SLA_SECONDS = 24 * 60 * 60; // 86400 seconds

interface RecallTimerProps {
  drill?: RecallDrill;
  onCancel?: () => void;
  onComplete?: () => void;
  onStartDrill?: () => void;
  className?: string;
}

export function RecallTimer({ drill, onCancel, onComplete, onStartDrill, className }: RecallTimerProps) {
  const [currentTime, setCurrentTime] = useState(Date.now());

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
        <CardContent className="pt-6">
          <div className="text-center py-8">
            <Timer className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
            <p className="text-muted-foreground">No active recall drill</p>
            <Button className="mt-4" variant="outline" onClick={onStartDrill} disabled={!onStartDrill}>
              <PlayCircle className="w-4 h-4 mr-2" />
              Start Mock Drill
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const status = statusConfig[drill.status];
  const StatusIcon = status.icon;

  return (
    <Card className={cn(
      'relative overflow-hidden',
      timeData?.urgency === 'critical' && 'border-re-danger',
      timeData?.urgency === 'warning' && 'border-re-warning',
      className
    )}>
      {/* Urgency overlay animation */}
      {timeData?.urgency === 'critical' && drill.status === 'IN_PROGRESS' && (
        <motion.div
          className="absolute inset-0 bg-re-danger-muted0/10 pointer-events-none"
          animate={{ opacity: [0.1, 0.3, 0.1] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
      )}

      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-re-danger" />
            FDA Recall Drill
          </CardTitle>
          <Badge className={cn(status.bgColor, status.color)}>
            <StatusIcon className="w-3 h-3 mr-1" />
            {status.label}
          </Badge>
        </div>
        <CardDescription>
          24-Hour SLA Compliance Tracking
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
          <p className="text-sm text-muted-foreground mt-2">
            Time Remaining to Meet FDA 24-Hour SLA
          </p>
        </div>

        {/* Progress Bar */}
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span>Elapsed</span>
            <span>{formatDuration(timeData?.elapsed || 0)}</span>
          </div>
          <div className="h-3 bg-muted rounded-full overflow-hidden">
            <motion.div
              className={cn(
                'h-full rounded-full',
                timeData?.urgency === 'breached' && 'bg-re-danger-muted0',
                timeData?.urgency === 'critical' && 'bg-re-danger-muted0',
                timeData?.urgency === 'warning' && 'bg-re-warning-muted0',
                timeData?.urgency === 'normal' && 'bg-re-success-muted0'
              )}
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, timeData?.progress || 0)}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>0h</span>
            <span>24h SLA</span>
          </div>
        </div>

        {/* Drill Details */}
        <div className="grid grid-cols-2 gap-4 pt-4 border-t">
          <div>
            <p className="text-sm text-muted-foreground">Target Lot</p>
            <p className="font-mono text-sm truncate">{drill.target_tlc}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Type</p>
            <p className="font-medium text-sm">{drill.type}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Facilities Contacted</p>
            <p className="font-medium text-sm">
              {drill.facilities_contacted} / {drill.total_facilities}
            </p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Lots Traced</p>
            <p className="font-medium text-sm">{drill.lots_traced}</p>
          </div>
        </div>

        {/* Actions */}
        {drill.status === 'IN_PROGRESS' && (
          <div className="flex gap-2 pt-4 border-t">
            {onComplete && (
              <Button className="flex-1" onClick={onComplete}>
                <CheckCircle className="w-4 h-4 mr-2" />
                Complete Drill
              </Button>
            )}
            {onCancel && (
              <Button variant="outline" onClick={onCancel}>
                <StopCircle className="w-4 h-4 mr-2" />
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
    normal: 'text-foreground',
    warning: 'text-re-warning',
    critical: 'text-re-danger',
    breached: 'text-re-danger',
  }[urgency];

  return (
    <div className={cn('font-mono text-6xl font-bold tabular-nums', colorClass)}>
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
      <span className={cn(isActive && 'animate-pulse')}>:</span>
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
      <span className={cn(isActive && 'animate-pulse')}>:</span>
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
  const StatusIcon = status.icon;

  useEffect(() => {
    if (drill.status !== 'IN_PROGRESS') return;

    const interval = setInterval(() => {
      setRemaining(r => Math.max(0, r - 1));
    }, 1000);

    return () => clearInterval(interval);
  }, [drill.status]);

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Badge className={cn(status.bgColor, status.color)}>
        <StatusIcon className="w-3 h-3 mr-1" />
        {status.label}
      </Badge>
      {showTimer && drill.status === 'IN_PROGRESS' && (
        <span className={cn(
          'font-mono text-sm',
          remaining <= 3600 ? 'text-re-danger' : 'text-muted-foreground'
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

  const color = percentage >= 90 ? 'stroke-re-brand' : percentage >= 70 ? 'stroke-amber-500' : 'stroke-re-danger';

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
          className="text-muted"
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
        <span className="text-2xl font-bold">{Math.round(percentage)}%</span>
        <span className="text-xs text-muted-foreground">SLA Met</span>
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
