'use client';

import { useQuery } from '@tanstack/react-query';
import { Shield, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';

interface VerificationResult {
    substation_id: string;
    latest_snapshot_id: string;
    content_hash_valid: boolean;
    signature_valid: boolean;
    chain_intact: boolean;
    status: 'verified' | 'corrupted';
    verified_at: string;
    previous_snapshot_id?: string;
}

interface VerificationWidgetProps {
    substationId: string;
}

function StatusIndicator({ label, valid }: { label: string; valid: boolean }) {
    return (
        <div className="flex items-center justify-between py-2 px-3 rounded-md bg-muted/50">
            <span className="text-sm font-medium">{label}</span>
            <div className="flex items-center gap-2">
                {valid ? (
                    <>
                        <CheckCircle2 className="h-4 w-4 text-green-600" />
                        <span className="text-xs text-green-600 font-medium">Valid</span>
                    </>
                ) : (
                    <>
                        <XCircle className="h-4 w-4 text-red-600" />
                        <span className="text-xs text-red-600 font-medium">Invalid</span>
                    </>
                )}
            </div>
        </div>
    );
}

export function VerificationWidget({ substationId }: VerificationWidgetProps) {
    const { data, isLoading, error, refetch } = useQuery<VerificationResult>({
        queryKey: ['verification', substationId],
        queryFn: async () => {
            const response = await fetch(`/api/energy/verify/latest/${substationId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        },
        refetchInterval: 60000, // Refresh every minute
        retry: 2,
    });

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <Skeleton className="h-6 w-48" />
                </CardHeader>
                <CardContent>
                    <div className="space-y-3">
                        <Skeleton className="h-12 w-full" />
                        <Skeleton className="h-12 w-full" />
                        <Skeleton className="h-12 w-full" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (error) {
        return (
            <Card className="border-muted bg-muted/20">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-muted-foreground text-base">
                        <AlertTriangle className="h-5 w-5" />
                        Verification Status Unavailable
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <p className="text-sm text-muted-foreground">
                        Unable to fetch real-time verification status. Click "Run Verification" on the dashboard to check chain integrity.
                    </p>
                </CardContent>
            </Card>
        );
    }

    if (!data) {
        return null;
    }

    const isVerified = data.status === 'verified';
    const borderColor = isVerified ? 'border-green-500' : 'border-red-500';

    return (
        <Card className={`${borderColor} border-2`}>
            <CardHeader>
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                        <Shield className={isVerified ? 'text-green-600' : 'text-red-600'} />
                        Chain Integrity Status
                    </CardTitle>
                    <Badge variant={isVerified ? 'default' : 'destructive'} className="font-mono">
                        {isVerified ? 'VERIFIED' : 'CORRUPTED'}
                    </Badge>
                </div>
                <CardDescription>
                    Last verified: {new Date(data.verified_at).toLocaleString()}
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                <div className="space-y-2">
                    <StatusIndicator
                        label="Content Hash Integrity"
                        valid={data.content_hash_valid}
                    />
                    <StatusIndicator
                        label="Cryptographic Signature"
                        valid={data.signature_valid}
                    />
                    <StatusIndicator
                        label="Chain Linkage"
                        valid={data.chain_intact}
                    />
                </div>

                {!isVerified && (
                    <Alert variant="destructive">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle>Chain Corruption Detected</AlertTitle>
                        <AlertDescription className="text-xs">
                            Critical integrity breach. Contact compliance team immediately.
                            Do not create new snapshots until resolved.
                        </AlertDescription>
                    </Alert>
                )}

                {isVerified && (
                    <div className="pt-2 border-t text-xs text-muted-foreground">
                        <p className="font-mono truncate">
                            Latest: {data.latest_snapshot_id}
                        </p>
                        {data.previous_snapshot_id && (
                            <p className="font-mono truncate">
                                Prev: {data.previous_snapshot_id}
                            </p>
                        )}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
