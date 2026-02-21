'use client';

import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Shield, CheckCircle2, XCircle, Activity } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface VerificationEvent {
    id: string;
    timestamp: string;
    status: 'verified' | 'corrupted';
    snapshots_checked: number;
    corrupted_count: number;
}

interface AuditHistoryTimelineProps {
    substationId: string;
    maxItems?: number;
}

export function AuditHistoryTimeline({ substationId, maxItems = 5 }: AuditHistoryTimelineProps) {
    // In a real implementation, this would fetch from a verification history endpoint
    // For now, we'll simulate by calling the verification endpoint and storing results
    const { data: verificationHistory, isLoading } = useQuery<VerificationEvent[]>({
        queryKey: ['audit-history', substationId],
        queryFn: async () => {
            // Simulate verification history
            // In production, this would be a dedicated /energy/verification/history endpoint
            const response = await fetch(`/api/energy/verify/recent?limit=${maxItems}`);
            if (!response.ok) {
                return [];
            }
            const result = await response.json();

            if (result.verified === 0 && result.corrupted === 0) {
                return [];
            }

            // Transform the response into history events
            return [{
                id: '1',
                timestamp: new Date().toISOString(),
                status: result.corrupted > 0 ? 'corrupted' : 'verified',
                snapshots_checked: result.verified + result.corrupted,
                corrupted_count: result.corrupted
            }];
        },
        refetchInterval: 300000, // Every 5 minutes
    });

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="text-sm font-medium">Verification History</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        {[...Array(3)].map((_, i) => (
                            <Skeleton key={i} className="h-16 w-full" />
                        ))}
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader>
                <div className="flex items-center gap-2">
                    <Activity className="h-4 w-4" />
                    <CardTitle className="text-sm font-medium">Verification History</CardTitle>
                </div>
            </CardHeader>
            <CardContent>
                {!verificationHistory || verificationHistory.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                        <Shield className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p className="text-sm">No verification history yet</p>
                        <p className="text-xs mt-1">Click "Run Verification" to start</p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {verificationHistory.map((audit) => (
                            <div
                                key={audit.id}
                                className={`flex items-start gap-4 border-l-2 pl-4 ${audit.status === 'verified' ? 'border-green-500' : 'border-red-500'
                                    }`}
                            >
                                <div className="flex-shrink-0 mt-1">
                                    {audit.status === 'verified' ? (
                                        <CheckCircle2 className="h-5 w-5 text-green-600" />
                                    ) : (
                                        <XCircle className="h-5 w-5 text-red-600" />
                                    )}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 mb-1">
                                        <span className="text-sm font-medium">
                                            {audit.status === 'verified' ? 'Chain Verified' : 'Corruption Detected'}
                                        </span>
                                        <Badge
                                            variant={audit.status === 'verified' ? 'default' : 'destructive'}
                                            className="text-xs"
                                        >
                                            {audit.snapshots_checked} snapshots
                                        </Badge>
                                    </div>
                                    <div className="text-xs text-muted-foreground space-y-0.5">
                                        <p>
                                            Checked: {audit.snapshots_checked} snapshots
                                            {audit.corrupted_count > 0 && ` • Failed: ${audit.corrupted_count}`}
                                        </p>
                                        <p>{formatDistanceToNow(new Date(audit.timestamp), { addSuffix: true })}</p>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
