'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { RecallReadiness } from '@/types/fsma';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
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
        <CardContent className="pt-6">
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!readiness) {
    return (
      <Card className={className}>
        <CardContent className="pt-6">
          <div className="text-center py-8 text-muted-foreground">
            <Shield className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>Unable to load compliance readiness</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Determine overall status
  const getOverallStatus = (score: number) => {
    if (score >= 90) return { label: 'Ready', color: 'text-re-success', bg: 'bg-re-success-muted', icon: CheckCircle };
    if (score >= 70) return { label: 'At Risk', color: 'text-re-warning', bg: 'bg-re-warning-muted', icon: AlertTriangle };
    return { label: 'Not Ready', color: 'text-re-danger', bg: 'bg-re-danger-muted', icon: XCircle };
  };

  const status = getOverallStatus(readiness.overall_score ?? 0);
  const StatusIcon = status.icon;

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
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Shield className="w-5 h-5" />
            FDA Recall Readiness
          </CardTitle>
          <div className="flex items-center gap-2">
            {onExportReport && (
              <Button variant="ghost" size="sm" onClick={onExportReport} title="Download Report">
                <Download className="w-4 h-4" />
              </Button>
            )}
            <Badge className={cn(status.bg, status.color)}>
              <StatusIcon className="w-3 h-3 mr-1" />
              {status.label}
            </Badge>
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
        <div className="grid grid-cols-3 gap-4 py-4 border-y">
          <div className="text-center">
            <p className="text-2xl font-bold">
              {typeof readiness.sla_compliance === 'object' && readiness.sla_compliance !== null
                ? ((readiness.sla_compliance as { rate_pct?: number }).rate_pct ?? 0)
                : (readiness.sla_compliance ?? 0)}%
            </p>
            <p className="text-xs text-muted-foreground">SLA Met</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold">{(readiness.average_response_time_hours ?? 0).toFixed(1)}h</p>
            <p className="text-xs text-muted-foreground">Avg Response</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold">{readiness.total_drills ?? 0}</p>
            <p className="text-xs text-muted-foreground">Total Drills</p>
          </div>
        </div>

        {/* Control Dimensions */}
        <div className="space-y-3">
          <h4 className="font-medium text-sm">Control Dimensions</h4>
          {controlDimensions.map((dim) => {
            const score = readiness.control_scores?.[dim.key as keyof typeof readiness.control_scores] ?? 0;
            const Icon = dim.icon;

            return (
              <div key={dim.key} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <Icon className="w-4 h-4 text-muted-foreground" />
                    <span>{dim.label}</span>
                    <span className="text-xs text-muted-foreground">({dim.weight})</span>
                  </div>
                  <span className={cn(
                    'font-medium',
                    score >= 80 ? 'text-re-success' : score >= 60 ? 'text-re-warning' : 'text-re-danger'
                  )}>
                    {score}%
                  </span>
                </div>
                <div className="h-2 bg-muted rounded-full overflow-hidden">
                  <motion.div
                    className={cn(
                      'h-full rounded-full',
                      score >= 80 ? 'bg-re-success-muted0' : score >= 60 ? 'bg-re-warning-muted0' : 'bg-re-danger-muted0'
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
          <div className="space-y-2 pt-4 border-t">
            <h4 className="font-medium text-sm flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-re-warning" />
              Recommendations
            </h4>
            <ul className="space-y-1">
              {readiness.recommendations.slice(0, 3).map((rec, i) => (
                <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                  <ChevronRight className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  {rec}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Action Button */}
        {onStartDrill && (
          <Button className="w-full" onClick={onStartDrill}>
            Start Mock Recall Drill
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

  const color = normalizedScore >= 90 ? 'stroke-re-brand' : normalizedScore >= 70 ? 'stroke-amber-500' : 'stroke-re-danger';
  const textColor = normalizedScore >= 90 ? 'text-re-success' : normalizedScore >= 70 ? 'text-re-warning' : 'text-re-danger';

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
          className="text-muted"
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
        <span className={cn('font-bold', config.text, textColor)}>{Math.round(normalizedScore)}</span>
        <span className="text-xs text-muted-foreground">/ 100</span>
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
  const status = score >= 90
    ? { label: 'Ready', color: 'bg-re-success-muted text-re-success', icon: CheckCircle }
    : score >= 70
      ? { label: 'At Risk', color: 'bg-re-warning-muted text-re-warning', icon: AlertTriangle }
      : { label: 'Not Ready', color: 'bg-re-danger-muted text-re-danger', icon: XCircle };

  const Icon = status.icon;

  return (
    <Badge className={cn(status.color, className)}>
      <Icon className="w-3 h-3 mr-1" />
      {score}% - {status.label}
    </Badge>
  );
}
