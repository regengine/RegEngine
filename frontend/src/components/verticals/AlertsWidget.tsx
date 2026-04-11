'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { AlertTriangle, Bell, CheckCircle, XCircle, Info, ExternalLink } from 'lucide-react';

export type AlertSeverity = 'CRITICAL' | 'WARNING' | 'INFO';

export interface Alert {
  id: string;
  severity: AlertSeverity;
  title: string;
  message: string;
  timestamp: string | Date;
  source?: string;
  actionUrl?: string;
  actionLabel?: string;
  dismissed?: boolean;
}

interface AlertsWidgetProps {
  alerts: Alert[];
  title?: string;
  maxVisible?: number;
  className?: string;
  onDismiss?: (alertId: string) => void;
  onActionClick?: (alert: Alert) => void;
  showDismissed?: boolean;
}

export function AlertsWidget({
  alerts,
  title = 'Active Alerts',
  maxVisible = 5,
  className,
  onDismiss,
  onActionClick,
  showDismissed = false,
}: AlertsWidgetProps) {
  const filteredAlerts = showDismissed
    ? alerts
    : alerts.filter(alert => !alert.dismissed);

  const displayAlerts = filteredAlerts.slice(0, maxVisible);
  const criticalCount = filteredAlerts.filter(a => a.severity === 'CRITICAL').length;
  const warningCount = filteredAlerts.filter(a => a.severity === 'WARNING').length;

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Bell className="w-5 h-5" />
            {title}
          </CardTitle>
          <div className="flex items-center gap-2">
            {criticalCount > 0 && (
              <Badge className="bg-re-danger-muted text-re-danger dark:bg-re-danger/30 dark:text-re-danger">
                {criticalCount} Critical
              </Badge>
            )}
            {warningCount > 0 && (
              <Badge className="bg-re-warning-muted text-re-warning dark:bg-re-warning/30 dark:text-re-warning">
                {warningCount} Warning
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {displayAlerts.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <CheckCircle className="w-12 h-12 mx-auto mb-4 text-re-success opacity-50" />
            <p className="font-medium">All clear!</p>
            <p className="text-sm">No active alerts</p>
          </div>
        ) : (
          <div className="space-y-2">
            {displayAlerts.map((alert, index) => (
              <AlertItem
                key={alert.id}
                alert={alert}
                index={index}
                onDismiss={onDismiss}
                onActionClick={onActionClick}
              />
            ))}
          </div>
        )}

        {filteredAlerts.length > maxVisible && (
          <div className="mt-4 pt-4 border-t text-center">
            <p className="text-sm text-muted-foreground">
              +{filteredAlerts.length - maxVisible} more alerts
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface AlertItemProps {
  alert: Alert;
  index: number;
  onDismiss?: (alertId: string) => void;
  onActionClick?: (alert: Alert) => void;
}

function AlertItem({ alert, index, onDismiss, onActionClick }: AlertItemProps) {
  const config = getSeverityConfig(alert.severity);
  const Icon = config.icon;

  const timestamp = typeof alert.timestamp === 'string'
    ? alert.timestamp
    : alert.timestamp.toISOString();

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className={cn(
        'flex items-start gap-3 p-3 rounded-lg border',
        config.borderColor,
        config.bgColor
      )}
    >
      <Icon className={cn('w-5 h-5 flex-shrink-0 mt-0.5', config.iconColor)} />

      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-start justify-between gap-2">
          <p className="font-medium text-sm">{alert.title}</p>
          {onDismiss && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0 flex-shrink-0"
              onClick={() => onDismiss(alert.id)}
            >
              <XCircle className="w-4 h-4" />
            </Button>
          )}
        </div>

        <p className="text-sm text-muted-foreground line-clamp-2">
          {alert.message}
        </p>

        <div className="flex items-center justify-between gap-2 pt-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{new Date(timestamp).toLocaleTimeString()}</span>
            {alert.source && (
              <>
                <span>•</span>
                <span>{alert.source}</span>
              </>
            )}
          </div>

          {alert.actionUrl && (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={() => onActionClick?.(alert)}
            >
              {alert.actionLabel || 'View'}
              <ExternalLink className="w-3 h-3 ml-1" />
            </Button>
          )}
        </div>
      </div>
    </motion.div>
  );
}

function getSeverityConfig(severity: AlertSeverity) {
  switch (severity) {
    case 'CRITICAL':
      return {
        icon: XCircle,
        iconColor: 'text-re-danger dark:text-re-danger',
        bgColor: 'bg-re-danger-muted dark:bg-re-danger/20',
        borderColor: 'border-re-danger dark:border-red-900',
      };
    case 'WARNING':
      return {
        icon: AlertTriangle,
        iconColor: 'text-re-warning dark:text-re-warning',
        bgColor: 'bg-re-warning-muted dark:bg-re-warning/20',
        borderColor: 'border-amber-200 dark:border-amber-900',
      };
    default:
      return {
        icon: Info,
        iconColor: 'text-re-info dark:text-re-info',
        bgColor: 'bg-re-info-muted dark:bg-re-info/20',
        borderColor: 'border-blue-200 dark:border-blue-900',
      };
  }
}
