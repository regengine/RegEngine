'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { MassBalanceResult, MassBalanceEvent } from '@/types/fsma';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Scale,
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
  className?: string;
}

export function MassBalanceWidget({ result, isLoading, className }: MassBalanceWidgetProps) {
  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="pt-6">
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!result) {
    return (
      <Card className={className}>
        <CardContent className="pt-6">
          <div className="text-center py-8 text-muted-foreground">
            <Scale className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>Enter a TLC to check mass balance</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const statusConfig = {
    BALANCED: {
      icon: CheckCircle,
      color: 'text-green-600',
      bgColor: 'bg-green-100 dark:bg-green-900/30',
      borderColor: 'border-green-500',
      label: 'Balanced',
    },
    WITHIN_TOLERANCE: {
      icon: AlertTriangle,
      color: 'text-amber-600',
      bgColor: 'bg-amber-100 dark:bg-amber-900/30',
      borderColor: 'border-amber-500',
      label: 'Within Tolerance',
    },
    MASS_IMBALANCE: {
      icon: XCircle,
      color: 'text-red-600',
      bgColor: 'bg-red-100 dark:bg-red-900/30',
      borderColor: 'border-red-500',
      label: 'Mass Imbalance',
    },
    // Default fallback for unknown status
    UNKNOWN: {
      icon: Scale,
      color: 'text-gray-600',
      bgColor: 'bg-gray-100 dark:bg-gray-900/30',
      borderColor: 'border-gray-500',
      label: 'Checking...',
    },
  };

  const config = statusConfig[result.status] || statusConfig.UNKNOWN;
  const StatusIcon = config.icon;

  // Calculate bar widths (max = larger of input or output, with fallback for zero)
  const maxQuantity = Math.max(result.input_quantity || 0, result.output_quantity || 0) || 1;
  const inputPercent = ((result.input_quantity || 0) / maxQuantity) * 100;
  const outputPercent = ((result.output_quantity || 0) / maxQuantity) * 100;

  return (
    <Card className={cn(config.borderColor, 'border-l-4', className)}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Scale className="w-5 h-5" />
            Mass Balance Check
          </CardTitle>
          <Badge className={cn(config.bgColor, config.color)}>
            <StatusIcon className="w-3 h-3 mr-1" />
            {config.label}
          </Badge>
        </div>
        <CardDescription className="font-mono text-xs">
          {result.lot_tlc}
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Visual Balance Display */}
        <div className="space-y-4">
          {/* Input Bar */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1">
                <ArrowDownCircle className="w-4 h-4 text-blue-500" />
                Input Quantity
              </span>
              <span className="font-mono">{result.input_quantity.toLocaleString()}</span>
            </div>
            <div className="h-4 bg-muted rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-blue-500 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${inputPercent}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
          </div>

          {/* Output Bar */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1">
                <ArrowUpCircle className="w-4 h-4 text-purple-500" />
                Output Quantity
              </span>
              <span className="font-mono">{result.output_quantity.toLocaleString()}</span>
            </div>
            <div className="h-4 bg-muted rounded-full overflow-hidden">
              <motion.div
                className="h-full bg-purple-500 rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${outputPercent}%` }}
                transition={{ duration: 0.5, delay: 0.1 }}
              />
            </div>
          </div>
        </div>

        {/* Variance Info */}
        <div className="grid grid-cols-3 gap-4 py-4 border-y">
          <div className="text-center">
            <p className="text-2xl font-bold">{result.variance.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">Variance</p>
          </div>
          <div className="text-center">
            <p className={cn(
              'text-2xl font-bold',
              Math.abs(result.variance_percent) > result.tolerance_percent ? 'text-red-600' : ''
            )}>
              {result.variance_percent.toFixed(1)}%
            </p>
            <p className="text-xs text-muted-foreground">Variance %</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold">{result.tolerance_percent}%</p>
            <p className="text-xs text-muted-foreground">Tolerance</p>
          </div>
        </div>

        {/* Time Violations */}
        {result.time_violations && result.time_violations.length > 0 && (
          <div className="space-y-2">
            <h4 className="font-medium flex items-center gap-2 text-red-600">
              <Clock className="w-4 h-4" />
              Time Violations Detected
            </h4>
            {result.time_violations.map((violation, i) => (
              <div key={i} className="p-2 rounded bg-red-50 dark:bg-red-900/20 text-sm">
                <p className="font-medium">{violation.violation_type.replace('_', ' ')}</p>
                <p className="text-muted-foreground text-xs">
                  {violation.source_time} → {violation.target_time}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Events List */}
        {result.events && result.events.length > 0 && (
          <div className="space-y-2">
            <h4 className="font-medium text-sm">Event Breakdown</h4>
            <div className="max-h-48 overflow-y-auto space-y-1">
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
    <div className="flex items-center gap-2 p-2 rounded bg-muted/50 text-sm">
      {isInbound ? (
        <ArrowDownCircle className="w-4 h-4 text-blue-500 flex-shrink-0" />
      ) : (
        <ArrowUpCircle className="w-4 h-4 text-purple-500 flex-shrink-0" />
      )}
      <div className="flex-1 min-w-0">
        <p className="truncate">{event.facility}</p>
        <p className="text-xs text-muted-foreground">{event.type}</p>
      </div>
      <div className="text-right">
        <p className="font-mono">{event.quantity.toLocaleString()}</p>
        <p className="text-xs text-muted-foreground">{event.timestamp}</p>
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
    BALANCED: { icon: CheckCircle, color: 'text-green-600' },
    WITHIN_TOLERANCE: { icon: AlertTriangle, color: 'text-amber-600' },
    MASS_IMBALANCE: { icon: XCircle, color: 'text-red-600' },
  }[status];

  const Icon = config.icon;

  return (
    <div className={cn('flex items-center gap-1', className)}>
      <Icon className={cn('w-4 h-4', config.color)} />
      <span className={cn('text-sm font-mono', config.color)}>
        {variancePercent > 0 ? '+' : ''}{variancePercent.toFixed(1)}%
      </span>
    </div>
  );
}
