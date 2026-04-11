'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { CheckCircle, AlertTriangle, XCircle, Clock, ChevronRight } from 'lucide-react';

export interface TimelineEvent {
    id: string;
    timestamp: string | Date;
    title: string;
    description?: string;
    type: 'success' | 'warning' | 'error' | 'info';
    metadata?: Record<string, unknown>;
    userName?: string;
}

interface ComplianceTimelineProps {
    events: TimelineEvent[];
    title?: string;
    maxItems?: number;
    className?: string;
    onEventClick?: (event: TimelineEvent) => void;
}

export function ComplianceTimeline({
    events,
    title = 'Activity Timeline',
    maxItems = 10,
    className,
    onEventClick,
}: ComplianceTimelineProps) {
    const displayEvents = events.slice(0, maxItems);

    return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Clock className="w-5 h-5" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {displayEvents.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Clock className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>No recent events</p>
          </div>
    ) : (
        <div className="space-y-0">
    {
        displayEvents.map((event, index) => (
            <TimelineEventItem
                key={event.id}
                event={event}
                isLast={index === displayEvents.length - 1}
                onClick={onEventClick}
            />
        ))
    }
          </div >
        )
}
      </CardContent >
    </Card >
  );
}

interface TimelineEventItemProps {
    event: TimelineEvent;
    isLast: boolean;
    onClick?: (event: TimelineEvent) => void;
}

function TimelineEventItem({ event, isLast, onClick }: TimelineEventItemProps) {
    const config = getEventConfig(event.type);
    const Icon = config.icon;

    const timestamp = typeof event.timestamp === 'string'
        ? event.timestamp
        : event.timestamp.toISOString();

    const formattedTime = formatTimestamp(timestamp);

    return (
        <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className={cn(
                'relative pl-8 pb-6',
                !isLast && 'border-l-2 border-muted ml-3',
                onClick && 'cursor-pointer hover:bg-muted/50 -ml-2 pl-10 pr-2 py-2 rounded-md transition-colors'
            )}
            onClick={() => onClick?.(event)}
        >
            {/* Icon */}
            <div
                className={cn(
                    'absolute left-0 top-1 w-6 h-6 rounded-full flex items-center justify-center',
                    config.bgColor
                )}
            >
                <Icon className={cn('w-3.5 h-3.5', config.iconColor)} />
            </div>

            {/* Content */}
            <div className="space-y-1">
            <div className="flex items-start justify-between gap-2">
            <p className="font-medium text-sm">{event.title}</p>
          {
        onClick && (
            <ChevronRight className="w-4 h-4 text-muted-foreground flex-shrink-0" />
          )
    }
        </div >

    {
        event.description && (
            <p className="text-sm text-muted-foreground line-clamp-2">
            { event.description }
          </p>
        )
}

<div className="flex items-center gap-2 text-xs text-muted-foreground">
    < span > { formattedTime }</span >
    {
        event.userName && (
            <>
                <span>•</span>
                <span>{event.userName}</span>
            </>
        )
    }
        </div >

{
    event.metadata && Object.keys(event.metadata).length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
            {
        Object.entries(event.metadata).slice(0, 3).map(([key, value]) => (
            <Badge key={key} variant="secondary" className="text-xs">
                { key }: { String(value) }
              </Badge >
            ))
    }
          </div>
        )}
      </div >
    </motion.div >
  );
}

function getEventConfig(type: TimelineEvent['type']) {
    switch (type) {
        case 'success':
            return {
                icon: CheckCircle,
                iconColor: 'text-re-success dark:text-re-success',
                bgColor: 'bg-re-success-muted dark:bg-re-success/30',
            };
        case 'warning':
            return {
                icon: AlertTriangle,
                iconColor: 'text-re-warning dark:text-re-warning',
                bgColor: 'bg-re-warning-muted dark:bg-re-warning/30',
            };
        case 'error':
            return {
                icon: XCircle,
                iconColor: 'text-re-danger dark:text-re-danger',
                bgColor: 'bg-re-danger-muted dark:bg-re-danger/30',
            };
        default:
            return {
                icon: Clock,
                iconColor: 'text-re-info dark:text-re-info',
                bgColor: 'bg-re-info-muted dark:bg-re-info/30',
            };
    }
}

function formatTimestamp(timestamp: string): string {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    });
}
