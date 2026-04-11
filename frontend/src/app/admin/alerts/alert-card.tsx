'use client';

import { DriftAlert } from '@/types/fsma';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { CheckCircle, Clock, AlertTriangle, XCircle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { formatDistanceToNow } from 'date-fns';

interface AlertCardProps {
    alert: DriftAlert;
    onAcknowledge: (id: string) => void;
}

export function AlertCard({ alert, onAcknowledge }: AlertCardProps) {
    const severityConfig = {
        CRITICAL: { icon: XCircle, color: 'text-re-danger', bg: 'bg-re-danger-muted dark:bg-re-danger/20', border: 'border-re-danger' },
        ERROR: { icon: XCircle, color: 'text-re-danger', bg: 'bg-re-danger-muted dark:bg-re-danger/20', border: 'border-re-danger' },
        WARNING: { icon: AlertTriangle, color: 'text-re-warning', bg: 'bg-re-warning-muted dark:bg-re-warning/20', border: 'border-re-warning' },
        INFO: { icon: Info, color: 'text-re-info', bg: 'bg-re-info-muted dark:bg-re-info/20', border: 'border-blue-200' },
    }[alert.severity] || { icon: Info, color: 'text-re-text-disabled', bg: 'bg-re-surface-card', border: 'border-re-border' };

    const Icon = severityConfig.icon;

    return (
        <Card className={cn('overflow-hidden transition-all hover:shadow-md', severityConfig.border)}>
            <CardHeader className={cn('py-3 px-4 border-b flex flex-row items-center justify-between', severityConfig.bg)}>
                <div className="flex items-center gap-2">
                    <Icon className={cn('w-4 h-4', severityConfig.color)} />
                    <span className={cn('font-semibold text-xs tracking-wider', severityConfig.color)}>
                        {alert.severity}
                    </span>
                </div>
                <span className="text-xs text-muted-foreground font-mono">
                    {alert.metric?.toUpperCase() || 'SYSTEM'}
                </span>
            </CardHeader>
            <CardContent className="p-4 space-y-3">
                <div>
                    <p className="font-medium text-sm text-foreground mb-1">
                        {alert.message}
                    </p>
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="w-3 h-3" />
                        {alert.created_at ? formatDistanceToNow(new Date(alert.created_at), { addSuffix: true }) : 'Just now'}
                    </div>
                </div>

                {alert.current_value !== undefined && alert.threshold !== undefined && (
                    <div className="text-xs bg-muted/50 p-2 rounded grid grid-cols-2 gap-2">
                        <div>
                            <span className="block text-muted-foreground">Current</span>
                            <span className="font-mono font-medium">{alert.current_value}</span>
                        </div>
                        <div>
                            <span className="block text-muted-foreground">Threshold</span>
                            <span className="font-mono font-medium">{alert.threshold}</span>
                        </div>
                    </div>
                )}
            </CardContent>
            <CardFooter className="p-3 pt-0 bg-muted/20">
                <Button
                    variant="ghost"
                    size="sm"
                    className="w-full text-xs hover:bg-white hover:shadow-sm"
                    onClick={() => onAcknowledge(alert.id)}
                >
                    <CheckCircle className="w-3 h-3 mr-2" />
                    Acknowledge
                </Button>
            </CardFooter>
        </Card>
    );
}
