'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { LucideIcon } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export interface MetricConfig {
    label: string;
    value: string | number;
    icon: LucideIcon;
    iconColor: string;
    iconBgColor: string;
    trend?: {
        value: number;
        isPositive: boolean;
    };
    helpText?: string;
}

interface ComplianceMetricsGridProps {
    metrics: MetricConfig[];
    columns?: 2 | 3 | 4 | 6;
    className?: string;
}

export function ComplianceMetricsGrid({
    metrics,
    columns = 4,
    className
}: ComplianceMetricsGridProps) {
    const gridCols = {
        2: 'grid-cols-1 md:grid-cols-2',
        3: 'grid-cols-1 md:grid-cols-3',
        4: 'grid-cols-2 md:grid-cols-4',
        6: 'grid-cols-2 md:grid-cols-3 lg:grid-cols-6',
    };

    return (
        <div className={cn('grid gap-4', gridCols[columns], className)}>
            {metrics.map((metric, index) => (
                <MetricCard key={index} metric={metric} index={index} />
            ))}
        </div>
    );
}

interface MetricCardProps {
    metric: MetricConfig;
    index: number;
}

function MetricCard({ metric, index }: MetricCardProps) {
    const Icon = metric.icon;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: index * 0.05 }}
        >
            <Card>
                <CardContent className="pt-6">
                <div className="flex items-center gap-3">
                <div className={cn('p-2.5 rounded-lg', metric.iconBgColor)}>
                    <Icon className={cn('h-6 w-6', metric.iconColor)} />
                </div>
                <div className="flex-1 min-w-0">
                <p className="text-2xl font-bold truncate">{metric.value}</p>
            <div className="flex items-center gap-2">
            <p className="text-sm text-muted-foreground truncate">
            {metric.label}
        </p>
                {
        metric.trend && (
            <span
                className={cn(
                    'text-xs font-medium',
                    metric.trend.isPositive ? 'text-green-600' : 'text-red-600'
                )}
            >
                {metric.trend.isPositive ? '+' : ''}
                {metric.trend.value}%
            </span>
        )
    }
              </div >
            </div >
          </div >
    {
        metric.helpText && (
            <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
              { metric.helpText }
            </p>
          )
}
        </CardContent >
      </Card >
    </motion.div >
  );
}
