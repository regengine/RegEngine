'use client';

import { cn } from '@/lib/utils';
import {
    Circle,
    CheckCircle2,
    AlertCircle,
    Calendar,
    Flag
} from 'lucide-react';

interface TimelineEvent {
    date: string;
    label: string;
    category: string;
    status: 'completed' | 'pending' | 'upcoming';
}

interface ComplianceTimelineProps {
    events: TimelineEvent[];
}

const categoryColors: Record<string, string> = {
    permits: 'bg-blue-500',
    minors: 'bg-red-500',
    insurance: 'bg-emerald-500',
    gate: 'bg-purple-500',
    production: 'bg-amber-500',
    labor: 'bg-orange-500',
    union: 'bg-indigo-500',
    safety: 'bg-pink-500',
};

export function ComplianceTimeline({ events }: ComplianceTimelineProps) {
    const formatDate = (dateStr: string) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    };

    const getDaysUntil = (dateStr: string) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diffTime = date.getTime() - now.getTime();
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
        return diffDays;
    };

    return (
        <div className="relative">
            {/* Horizontal Timeline */}
            <div className="flex items-center overflow-x-auto pb-4 gap-2">
                {events.map((event, index) => {
                    const daysUntil = getDaysUntil(event.date);
                    const isUrgent = daysUntil <= 3 && event.status !== 'completed';
                    const isPast = daysUntil < 0;
                    const categoryColor = categoryColors[event.category] || 'bg-slate-500';

                    return (
                        <div key={index} className="flex-shrink-0 relative group">
                            {/* Connector Line */}
                            {index < events.length - 1 && (
                                <div className="absolute top-4 left-1/2 w-full h-0.5 bg-slate-200 dark:bg-slate-700 z-0" />
                            )}

                            {/* Event Node */}
                            <div className="relative z-10 flex flex-col items-center">
                                <div className={cn(
                                    'w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all',
                                    event.status === 'completed'
                                        ? 'bg-emerald-100 border-emerald-500'
                                        : isUrgent
                                            ? 'bg-red-100 border-red-500 animate-pulse'
                                            : 'bg-white dark:bg-slate-800 border-slate-300 dark:border-slate-600',
                                    'group-hover:scale-110'
                                )}>
                                    {event.status === 'completed' ? (
                                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                                    ) : isUrgent ? (
                                        <AlertCircle className="h-4 w-4 text-red-500" />
                                    ) : event.category === 'production' ? (
                                        <Flag className="h-4 w-4 text-amber-500" />
                                    ) : (
                                        <Circle className="h-4 w-4 text-slate-400" />
                                    )}
                                </div>

                                {/* Category Indicator */}
                                <div className={cn(
                                    'w-2 h-2 rounded-full mt-1',
                                    categoryColor
                                )} />

                                {/* Label Card */}
                                <div className={cn(
                                    'mt-2 px-3 py-2 rounded-lg text-center min-w-[120px] max-w-[150px] transition-all',
                                    event.status === 'completed'
                                        ? 'bg-emerald-50 dark:bg-emerald-900/20'
                                        : isUrgent
                                            ? 'bg-red-50 dark:bg-red-900/20'
                                            : 'bg-slate-50 dark:bg-slate-800',
                                    'group-hover:shadow-md'
                                )}>
                                    <p className={cn(
                                        'text-xs font-medium',
                                        isUrgent ? 'text-red-600' : 'text-slate-700 dark:text-slate-300'
                                    )}>
                                        {formatDate(event.date)}
                                    </p>
                                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                                        {event.label}
                                    </p>
                                    {!isPast && event.status !== 'completed' && (
                                        <p className={cn(
                                            'text-[10px] mt-1',
                                            isUrgent ? 'text-red-500 font-medium' : 'text-muted-foreground'
                                        )}>
                                            {daysUntil === 0 ? 'Today!' : daysUntil === 1 ? 'Tomorrow' : `${daysUntil} days`}
                                        </p>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 pt-2 border-t text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                    <span>Completed</span>
                </div>
                <div className="flex items-center gap-1">
                    <Circle className="h-3 w-3 text-slate-400" />
                    <span>Pending</span>
                </div>
                <div className="flex items-center gap-1">
                    <AlertCircle className="h-3 w-3 text-red-500" />
                    <span>Urgent</span>
                </div>
                <div className="flex items-center gap-1">
                    <Flag className="h-3 w-3 text-amber-500" />
                    <span>Milestone</span>
                </div>
            </div>
        </div>
    );
}
