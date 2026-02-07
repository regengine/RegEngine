'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface ComplianceScoreGaugeProps {
    score: number;
    label?: string;
    size?: 'sm' | 'md' | 'lg';
    showTrend?: boolean;
    trend?: number;
    className?: string;
}

export function ComplianceScoreGauge({
    score,
    label = 'Compliance Score',
    size = 'md',
    showTrend = false,
    trend,
    className,
}: ComplianceScoreGaugeProps) {
    // Normalize score
    const normalizedScore = Math.max(0, Math.min(100, score || 0));

    const sizes = {
        sm: { outer: 100, stroke: 8, text: 'text-2xl', labelText: 'text-xs' },
        md: { outer: 140, stroke: 10, text: 'text-3xl', labelText: 'text-sm' },
        lg: { outer: 180, stroke: 12, text: 'text-4xl', labelText: 'text-base' },
    };

    const config = sizes[size];
    const radius = (config.outer - config.stroke) / 2;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (normalizedScore / 100) * circumference;

    // Determine color based on score
    const getColor = (score: number) => {
        if (score >= 90) return { stroke: 'stroke-green-500', text: 'text-green-600' };
        if (score >= 75) return { stroke: 'stroke-blue-500', text: 'text-blue-600' };
        if (score >= 60) return { stroke: 'stroke-amber-500', text: 'text-amber-600' };
        return { stroke: 'stroke-red-500', text: 'text-red-600' };
    };

    const colors = getColor(normalizedScore);

    const getTrendIcon = () => {
        if (!trend || trend === 0) return Minus;
        return trend > 0 ? TrendingUp : TrendingDown;
    };

    const TrendIcon = getTrendIcon();
    const trendColor = !trend || trend === 0
        ? 'text-gray-500'
        : trend > 0
            ? 'text-green-600'
            : 'text-red-600';

    return (
        <div className={cn('flex flex-col items-center', className)}>
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
            className={colors.stroke}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset }}
            transition={{ duration: 1, ease: 'easeOut' }}
            style={{ strokeDasharray: circumference }}
          />
        </svg>

        {/* Score display */ }
    <div className="absolute inset-0 flex flex-col items-center justify-center">
        < span className = { cn('font-bold', config.text, colors.text) } >
            { Math.round(normalizedScore) }
          </span >
        <span className="text-xs text-muted-foreground">/ 100</span>
        </div >
      </div >

        {/* Label */ }
        < div className ="mt-3 text-center">
            < p className = { cn('font-medium', config.labelText) } > { label }</p >
                { showTrend && trend !== undefined && (
                    <div className={cn('flex items-center justify-center gap-1 mt-1', trendColor)}>
                        <TrendIcon className="w-3 h-3" />
                        <span className="text-xs font-medium">
                        {trend > 0 ? '+' : ''}{trend}%
                    </span>
          </div >
        )
}
      </div >
    </div >
  );
}
