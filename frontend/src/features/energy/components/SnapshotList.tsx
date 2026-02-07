'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Database, ChevronRight } from 'lucide-react';
import { SnapshotDetailModal } from './SnapshotDetailModal';

interface Snapshot {
    id: string;
    snapshot_time: string;
    system_status: string;
    content_hash: string;
    generated_by: string;
}

interface SnapshotListProps {
    substationId: string;
    maxItems?: number;
}

export function SnapshotList({ substationId, maxItems = 5 }: SnapshotListProps) {
    const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);

    const { data, isLoading } = useQuery<{ snapshots: Snapshot[]; total: number }>({
        queryKey: ['snapshots', substationId],
        queryFn: async () => {
            const response = await fetch(
                `/api/energy/snapshots?substation_id=${substationId}&limit=${maxItems}`
            );
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        },
        refetchInterval: 120000, // Refresh every 2 minutes
    });

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="text-sm font-medium">Recent Snapshots</CardTitle>
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

    const snapshots = data?.snapshots || [];

    return (
        <>
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <CardTitle className="text-sm font-medium">Recent Snapshots</CardTitle>
                        <Badge variant="outline">{data?.total || 0} total</Badge>
                    </div>
                </CardHeader>
                <CardContent>
                    {snapshots.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            <Database className="h-12 w-12 mx-auto mb-2 opacity-50" />
                            <p className="text-sm">No snapshots found</p>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            {snapshots.map((snapshot) => (
                                <button
                                    key={snapshot.id}
                                    onClick={() => setSelectedSnapshotId(snapshot.id)}
                                    className="w-full p-3 rounded-lg border hover:bg-muted/50 transition-colors text-left group"
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 mb-1">
                                                <Database className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                                <span className="text-xs font-mono truncate">
                                                    {snapshot.id.slice(0, 8)}...
                                                </span>
                                                <Badge
                                                    variant={snapshot.system_status === 'NOMINAL' ? 'default' : 'destructive'}
                                                    className="text-xs"
                                                >
                                                    {snapshot.system_status}
                                                </Badge>
                                            </div>
                                            <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                                <span>{new Date(snapshot.snapshot_time).toLocaleString()}</span>
                                                <span className="truncate">By: {snapshot.generated_by}</span>
                                            </div>
                                        </div>
                                        <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:translate-x-1 transition-transform flex-shrink-0" />
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            {selectedSnapshotId && (
                <SnapshotDetailModal
                    snapshotId={selectedSnapshotId}
                    onClose={() => setSelectedSnapshotId(null)}
                />
            )}
        </>
    );
}
