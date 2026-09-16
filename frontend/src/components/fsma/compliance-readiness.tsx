'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { RecallReadiness } from '@/types/fsma';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import {
  AlertTriangle,
  Shield,
  Clock,
  FileText,
  Database,
  Cpu,
  TrendingUp,
  ChevronRight,
  Download,
} from 'lucide-react';

interface ComplianceReadinessProps {
  readiness?: RecallReadiness;
  isLoading?: boolean;
  onStartDrill?: () => void;
  onExportReport?: () => void;
  className?: string;
}

export function ComplianceReadiness({ readiness, isLoading, onStartDrill, onExportReport, className }: ComplianceReadinessProps) {
  if (isLoading) {
    return (
      <Card className={className}>
        <CardContent className="space-y-3" aria-busy="true">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-28 w-28 rounded-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!readiness || readiness.overall_score == null) {
    return (
      <Card className={className}>
        <CardContent>
          <EmptyState
            bare
            icon={Shield}
            title={readiness ? "Compliance readiness has not been measured" : "Unable to load compliance readiness"}
          />
        </CardContent>
      </Card>
    );
  }

  // Determine overall status
  const getOverallStatus = (score: number): { label: string; state: ComplianceState } => {
    if (score >= 90) return { label: 'Ready', state: 'compliant' };
    if (score >= 70) return { label: 'At Risk', state: 'at-risk' };
    return { label: 'Not Ready', state: 'non-compliant' };
  };

  const status = getOverallStatus(readiness.overall_score ?? 0);

  // Control dimension configuration
  const controlDimensions = [
    {
      key: 'traceability_plan',
      label: 'Traceability Plan',
      weight: '20%',
      icon: FileText,
      description: 'Governance, training, digital workflows',
    },
    {
      key: 'kde_capture',
      label: 'KDE Capture',
      weight: '25%',
      icon: Database,
      description: 'Data completeness for receiving, transforming, shipping',
    },
    {
      key: 'cte_coverage',
      label: 'CTE Coverage',
      weight: '20%',
      icon: TrendingUp,
      description: 'Critical tracking events mapped',
    },
    {
      key: 'recordkeeping',
      label: 'Recordkeeping',
      weight: '15%',
      icon: Clock,
      description: '2-year retention, <24hr retrieval',
    },
    {
      key: 'technology',
      label: 'Technology',
      weight: '15%',
      icon: Cpu,
      description: 'API access, serialization capabilities',
    },
  ];

  return (
    <Card className={className}>
      <CardHeader className="flex-col items-stretch gap-1">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
            FDA Recall Readiness
          </CardTitle>
          <div className="flex items-center gap-2">
            {onExportReport && (
              <Button
                variant="ghost"
                size="icon"
                onClick={onExportReport}
                title="Download Report"
                aria-label="Download Report"
              >
                <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </Button>
            )}
            <StatusBadge state={status.state} label={status.label} />
          </div>
        </div>
        <CardDescription>
          FSMA 204 Compliance Assessment
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Overall Score Gauge */}
        <div className="flex items-center justify-center py-4">
          <ReadinessGauge score={readiness.overall_score ?? 0} />
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-3 gap-4 border-y border-re-border-subtle py-4">
          <div>
            <p className="text-label text-re-text-muted">SLA Met</p>
            <p className="mt-1 text-title tabular-nums text-re-text-primary">
              {typeof readiness.sla_compliance === 'object' && readiness.sla_compliance !== null
                ? ((readiness.sla_compliance as { rate_pct?: number }).rate_pct ?? 0)
                : (readiness.sla_compliance ?? 0)}%
            </p>
          </div>
          <div>
            <p className="text-label text-re-text-muted">Avg Response</p>
            <p className="mt-1 text-title tabular-nums text-re-text-primary">{(readiness.average_response_time_hours ?? 0).toFixed(1)}h</p>
          </div>
          <div>
            <p className="text-label text-re-text-muted">Total Drills</p>
            <p className="mt-1 text-title tabular-nums text-re-text-primary">{readiness.total_drills ?? 0}</p>
          </div>
        </div>

        {/* Control Dimensions */}
        <div className="space-y-3">
          <h4 className="text-subheading text-re-text-primary">Control Dimensions</h4>
          {controlDimensions.map((dim) => {
            const score = readiness.control_scores?.[dim.key as keyof typeof readiness.control_scores] ?? 0;
            const Icon = dim.icon;

            return (
              <div key={dim.key} className="space-y-1">
                <div className="flex items-center justify-between gap-3 text-ui">
                  <div className="flex min-w-0 items-center gap-2">
                    <Icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                    <span className="truncate text-re-text-secondary">{dim.label}</span>
                    <span className="text-small text-re-text-tertiary">({dim.weight})</span>
                  </div>
                  <span className="font-medium tabular-nums text-re-text-primary">
                    {score}%
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-re-surface-inset">
                  <motion.div
                    className={cn(
                      'h-full rounded-full',
                      score >= 80 ? 'bg-re-success' : score >= 60 ? 'bg-re-warning' : 'bg-re-danger'
                    )}
                    initial={{ width: 0 }}
                    animate={{ width: `${score}%` }}
                    transition={{ duration: 0.5, delay: 0.1 }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Recommendations */}
        {readiness.recommendations && readiness.recommendations.length > 0 && (
          <div className="space-y-2 border-t border-re-border-subtle pt-4">
            <h4 className="flex items-center gap-2 text-subheading text-re-text-primary">
              <AlertTriangle className="h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
              Recommendations
            </h4>
            <ul className="space-y-1">
              {readiness.recommendations.slice(0, 3).map((rec, i) => (
                <li key={i} className="flex items-start gap-2 text-ui text-re-text-secondary">
                  <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                  {rec}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Action Button */}
        {onStartDrill && (
          <Button className="w-full" onClick={onStartDrill}>
            Run Recall Drill
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// Readiness gauge component
interface ReadinessGaugeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
}

function ReadinessGauge({ score, size = 'md' }: ReadinessGaugeProps) {
  // Normalize score to handle undefined/NaN cases
  const normalizedScore = isNaN(score) || score === undefined || score === null ? 0 : score;

  const sizes = {
    sm: { outer: 80, stroke: 6, text: 'text-xl' },
    md: { outer: 120, stroke: 8, text: 'text-3xl' },
    lg: { outer: 160, stroke: 10, text: 'text-4xl' },
  };

  const config = sizes[size];
  const radius = (config.outer - config.stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (normalizedScore / 100) * circumference;

  const color = normalizedScore >= 90 ? 'stroke-re-success' : normalizedScore >= 70 ? 'stroke-re-warning' : 'stroke-re-danger';

  return (
    <div className="relative" style={{ width: config.outer, height: config.outer }}>
      <svg
        className="transform -rotate-90"
        width={config.outer}
        height={config.outer}
        viewBox={`0 0 ${config.outer} ${config.outer}`}
      >
        {/* Background circle */}
        <circle
          cx={config.outer / 2}
          cy={config.outer / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={config.stroke}
          className="text-re-border-subtle"
        />
        {/* Progress circle */}
        <motion.circle
          cx={config.outer / 2}
          cy={config.outer / 2}
          r={radius}
          fill="none"
          strokeWidth={config.stroke}
          strokeLinecap="round"
          className={color}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1, ease: 'easeOut' }}
          style={{ strokeDasharray: circumference }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn('font-semibold tabular-nums text-re-text-primary', config.text)}>{Math.round(normalizedScore)}</span>
        <span className="text-label text-re-text-muted">/ 100</span>
      </div>
    </div>
  );
}

// Mini readiness badge for compact views
interface ReadinessBadgeProps {
  score: number;
  className?: string;
}

export function ReadinessBadge({ score, className }: ReadinessBadgeProps) {
  const status: { label: string; state: ComplianceState } = score >= 90
    ? { label: 'Ready', state: 'compliant' }
    : score >= 70
      ? { label: 'At Risk', state: 'at-risk' }
      : { label: 'Not Ready', state: 'non-compliant' };

  return (
    <StatusBadge
      state={status.state}
      label={`${score}% - ${status.label}`}
      className={className}
    />
  );
}
