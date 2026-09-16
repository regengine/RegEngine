'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { MassBalanceResult, MassBalanceEvent } from '@/types/fsma';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import {
  Scale,
  ArrowRight,
  CheckCircle,
  AlertTriangle,
  XCircle,
  ArrowDownCircle,
  ArrowUpCircle,
  Clock,
} from 'lucide-react';

interface MassBalanceWidgetProps {
  result?: MassBalanceResult;
  isLoading?: boolean;
  notImplemented?: boolean;
  className?: string;
}

export function MassBalanceWidget({ result, isLoading, notImplemented, className }: MassBalanceWidgetProps) {
  if (notImplemented) {
    return (
      <Card className={className}>
        <CardContent>
          <EmptyState
            bare
            icon={Scale}
            title="Mass balance validation is not yet available."
            description="Use chain integrity verification instead to validate your traceability records."
            action={
              <Button variant="secondary" size="sm" asChild>
                <a href="/tools/knowledge-graph">
                  Go to Chain Integrity View
                  <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                </a>
              </Button>
            }
          />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="space-y-3" aria-busy="true">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!result) {
    return (
      <Card className={className}>
        <CardContent>
          <EmptyState bare icon={Scale} title="Enter a TLC to check mass balance" />
        </CardContent>
      </Card>
    );
  }

  const statusConfig: Record<string, { state: ComplianceState; label: string }> = {
    BALANCED: { state: 'compliant', label: 'Balanced' },
    WITHIN_TOLERANCE: { state: 'at-risk', label: 'Within Tolerance' },
    MASS_IMBALANCE: { state: 'non-compliant', label: 'Mass Imbalance' },
    // Default fallback for unknown status
    UNKNOWN: { state: 'unknown', label: 'Checking...' },
  };

  const config = statusConfig[result.status] || statusConfig.UNKNOWN;

  // Calculate bar widths (max = larger of input or output, with fallback for zero)
  const maxQuantity = Math.max(result.input_quantity || 0, result.output_quantity || 0) || 1;
  const inputPercent = ((result.input_quantity || 0) / maxQuantity) * 100;
  const outputPercent = ((result.output_quantity || 0) / maxQuantity) * 100;

  return (
    <Card className={className}>
      <CardHeader className="flex-col items-stretch gap-1">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Scale className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            Mass Balance Check
          </CardTitle>
          <StatusBadge state={config.state} label={config.label} />
        </div>
        <CardDescription className="font-mono text-[0.8125rem]">
          {result.lot_tlc}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Visual Balance Display */}
        <div className="space-y-4">
          {/* Input Bar */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-ui text-re-text-secondary">
              <span className="flex items-center gap-1.5">
                <ArrowDownCircle className="h-4 w-4 text-re-cat-1" strokeWidth={1.75} aria-hidden="true" />
                Input Quantity
              </span>
              <span className="font-mono tabular-nums text-re-text-primary">{result.input_quantity.toLocaleString()}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-re-surface-inset">
              <motion.div
                className="h-full rounded-full bg-re-cat-1"
                initial={{ width: 0 }}
                animate={{ width: `${inputPercent}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>

          {/* Output Bar */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-ui text-re-text-secondary">
              <span className="flex items-center gap-1.5">
                <ArrowUpCircle className="h-4 w-4 text-re-cat-4" strokeWidth={1.75} aria-hidden="true" />
                Output Quantity
              </span>
              <span className="font-mono tabular-nums text-re-text-primary">{result.output_quantity.toLocaleString()}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-re-surface-inset">
              <motion.div
                className="h-full rounded-full bg-re-cat-4"
                initial={{ width: 0 }}
                animate={{ width: `${outputPercent}%` }}
                transition={{ duration: 0.5, delay: 0.1 }}
              />
            </div>
          </div>
        </div>

        {/* Variance Info */}
        <div className="grid grid-cols-3 gap-4 border-y border-re-border-subtle py-4">
          <div>
            <p className="text-label text-re-text-muted">Variance</p>
            <p className="mt-1 text-title tabular-nums text-re-text-primary">{result.variance.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-label text-re-text-muted">Variance %</p>
            <p className="mt-1 flex items-center gap-1.5 text-title tabular-nums text-re-text-primary">
              {Math.abs(result.variance_percent) > result.tolerance_percent && (
                <AlertTriangle className="h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
              )}
              {result.variance_percent.toFixed(1)}%
            </p>
          </div>
          <div>
            <p className="text-label text-re-text-muted">Tolerance</p>
            <p className="mt-1 text-title tabular-nums text-re-text-primary">{result.tolerance_percent}%</p>
          </div>
        </div>

        {/* Time Violations */}
        {result.time_violations && result.time_violations.length > 0 && (
          <div className="space-y-2">
            <h4 className="flex items-center gap-2 text-subheading text-re-text-primary">
              <Clock className="h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
              Time Violations Detected
            </h4>
            {result.time_violations.map((violation, i) => (
              <div key={i} className="rounded-md border border-l-[3px] border-re-border border-l-re-danger bg-re-surface-card px-3 py-2 text-ui">
                <p className="font-medium text-re-text-primary">{violation.violation_type.replace('_', ' ')}</p>
                <p className="font-mono text-[0.8125rem] text-re-text-tertiary">
                  {violation.source_time} → {violation.target_time}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Events List */}
        {result.events && result.events.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-subheading text-re-text-primary">Event Breakdown</h4>
            <div className="max-h-48 space-y-1 overflow-y-auto">
              {result.events.map((event, i) => (
                <MassBalanceEventRow key={i} event={event} />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface MassBalanceEventRowProps {
  event: MassBalanceEvent;
}

function MassBalanceEventRow({ event }: MassBalanceEventRowProps) {
  const isInbound = event.direction === 'IN';

  return (
    <div className="flex items-center gap-2 rounded-md bg-re-surface-inset px-3 py-2 text-ui">
      {isInbound ? (
        <ArrowDownCircle className="h-4 w-4 shrink-0 text-re-cat-1" strokeWidth={1.75} aria-hidden="true" />
      ) : (
        <ArrowUpCircle className="h-4 w-4 shrink-0 text-re-cat-4" strokeWidth={1.75} aria-hidden="true" />
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-re-text-primary">{event.facility}</p>
        <p className="text-small text-re-text-tertiary">{event.type}</p>
      </div>
      <div className="text-right">
        <p className="font-mono tabular-nums text-re-text-primary">{event.quantity.toLocaleString()}</p>
        <p className="font-mono text-[0.8125rem] text-re-text-tertiary">{event.timestamp}</p>
      </div>
    </div>
  );
}

// Mini mass balance indicator for compact views
interface MassBalanceIndicatorProps {
  status: MassBalanceResult['status'];
  variancePercent: number;
  className?: string;
}

export function MassBalanceIndicator({ status, variancePercent, className }: MassBalanceIndicatorProps) {
  const config = {
    BALANCED: { icon: CheckCircle, color: 'text-re-success' },
    WITHIN_TOLERANCE: { icon: AlertTriangle, color: 'text-re-warning' },
    MASS_IMBALANCE: { icon: XCircle, color: 'text-re-danger' },
  }[status];

  const Icon = config.icon;

  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <Icon className={cn('h-4 w-4 shrink-0', config.color)} strokeWidth={1.75} aria-hidden="true" />
      <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-secondary">
        {variancePercent > 0 ? '+' : ''}{variancePercent.toFixed(1)}%
      </span>
    </div>
  );
}
