'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { Activity, CheckCircle, AlertTriangle, XCircle, RefreshCw } from 'lucide-react';

export type HealthStatus = 'HEALTHY' | 'DEGRADED' | 'CRITICAL' | 'UNKNOWN';

export interface SystemHealth {
    status: HealthStatus;
    message?: string;
    lastCheck?: string;
    uptime?: string;
    activeAlerts?: number;
}

interface RealTimeMonitorProps {
    title: string;
    description?: string;
    health: SystemHealth;
    stats?: {
        label: string;
        value: string | number;
        status?: 'ok' | 'warning' | 'error';
    }[];
    className?: string;
    onRefresh?: () => void;
    isRefreshing?: boolean;
}

export function RealTimeMonitor({
    title,
    description,
    health,
    stats,
    className,
    onRefresh,
    isRefreshing = false,
}: RealTimeMonitorProps) {
    const statusConfig = getStatusConfig(health.status);

    return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-lg">{title}</CardTitle>
            <AnimatePresence mode="wait">
        < motion.div
    key = { health.status }
    initial = {{ scale: 0 }
}
animate = {{ scale: 1 }}
exit = {{ scale: 0 }}
transition = {{ duration: 0.2 }}
              >
    <div className={cn('w-2 h-2 rounded-full', statusConfig.dotColor)} />
              </motion.div >
            </AnimatePresence >
          </div >
    <Badge className={cn(statusConfig.bgColor, statusConfig.textColor)}>
        <statusConfig.icon className="w-3 h-3 mr-1" />
        {statusConfig.label}
    </Badge>
        </div >
    { description && (
        <CardDescription>{description}</CardDescription>
    )}
      </CardHeader >

    <CardContent className="space-y-4">
{/* Health Message */ }
{
    health.message && (
        <div className="text-sm text-muted-foreground">
    { health.message }
          </div >
        )
}

{/* Stats Grid */ }
{
    stats && stats.length > 0 && (
        <div className="grid grid-cols-2 gap-4 pt-2 border-t">
    {
        stats.map((stat, index) => (
            <div key={index} className="space-y-1">
        < p className ="text-xs text-muted-foreground">{stat.label}</p>
        < div className ="flex items-center gap-2">
        < p className ="text-lg font-semibold">{stat.value}</p>
                  {
                stat.status && (
                    <StatusDot status={stat.status} />
                )
            }
                </div >
              </div >
            ))
    }
          </div >
        )
}

{/* Footer Info */ }
<div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t">
    <span>
{ health.lastCheck ? `Last check: ${health.lastCheck}` : 'Monitoring...' }
          </span >
    { onRefresh && (
        <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1 hover:text-foreground transition-colors disabled:opacity-50"
                >
                <RefreshCw className={cn('w-3 h-3', isRefreshing && 'animate-spin')} />
Refresh
            </button >
          )}
        </div >
      </CardContent >
    </Card >
  );
}

function getStatusConfig(status: HealthStatus) {
    switch (status) {
        case 'HEALTHY':
            return {
                label: 'Operational',
                icon: CheckCircle,
                textColor: 'text-green-700 dark:text-green-400',
                bgColor: 'bg-green-100 dark:bg-green-900/30',
                dotColor: 'bg-green-500 animate-pulse',
            };
        case 'DEGRADED':
            return {
                label: 'Degraded',
                icon: AlertTriangle,
                textColor: 'text-amber-700 dark:text-amber-400',
                bgColor: 'bg-amber-100 dark:bg-amber-900/30',
                dotColor: 'bg-amber-500 animate-pulse',
            };
        case 'CRITICAL':
            return {
                label: 'Critical',
                icon: XCircle,
                textColor: 'text-red-700 dark:text-red-400',
                bgColor: 'bg-red-100 dark:bg-red-900/30',
                dotColor: 'bg-red-500 animate-pulse',
            };
        default:
            return {
                label: 'Unknown',
                icon: Activity,
                textColor: 'text-gray-700 dark:text-gray-400',
                bgColor: 'bg-gray-100 dark:bg-gray-900/30',
                dotColor: 'bg-gray-500',
            };
    }
}

function StatusDot({ status }: { status: 'ok' | 'warning' | 'error' }) {
    const colors = {
        ok: 'bg-green-500',
        warning: 'bg-amber-500',
        error: 'bg-red-500',
    };

    return <div className={cn('w-1.5 h-1.5 rounded-full', colors[status])} />;
}
