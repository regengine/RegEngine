'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { AnalysisSummary } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { Shield, Database, Lock, Search } from 'lucide-react';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardDescription, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';

export default function AnalysisResultClient() {
    const params = useParams();
    const { apiKey } = useAuth();
    const [data, setData] = useState<AnalysisSummary | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!params.id || !apiKey) return;

        apiClient.getDocumentAnalysis(params.id as string, apiKey)
            .then(setData)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, [params.id, apiKey]);

    if (loading) {
        return (
            <PageContainer>
                <div className="space-y-6" aria-busy="true">
                    <div className="space-y-3 border-b border-re-border-subtle pb-5">
                        <Skeleton className="h-8 w-80" />
                        <Skeleton className="h-4 w-64" />
                    </div>
                    <p className="text-ui text-re-text-tertiary">Loading Chain of Trust...</p>
                    <div className="grid gap-6 md:grid-cols-2">
                        <Skeleton className="h-80 w-full" />
                        <Skeleton className="h-48 w-full" />
                    </div>
                </div>
            </PageContainer>
        );
    }

    if (!data) {
        return (
            <PageContainer>
                <EmptyState icon={Search} title="Document Not Found" />
            </PageContainer>
        );
    }

    const steps = [
        {
            title: "Genesis Block (Ingestion)",
            icon: Database,
            status: "complete",
            hash: "0x8f7d...9a12", // Simulated
            time: "0s"
        },
        {
            title: "Compliance Analysis",
            icon: Search,
            status: "complete",
            hash: "0x3b2c...1d4e",
            time: "+1.2s"
        },
        {
            title: "Evidence Snapshot",
            icon: Lock,
            status: "complete",
            hash: "0x9e8f...7c6b",
            time: "+1.5s"
        },
        {
            title: "Hash-Chain Anchor",
            icon: Shield,
            status: "pending",
            hash: "Waiting...",
            time: "..."
        }
    ];

    return (
        <PageContainer>
            <PageHeader
                className="print:hidden"
                title="Chain of Trust Evidence"
                description={
                    <>Document ID: <code className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem]">{data.document_id}</code></>
                }
                meta={
                    <Badge variant={data.risk_score > 50 ? 'destructive' : 'default'}>
                        Risk Score: {data.risk_score}/100
                    </Badge>
                }
            />

            <div className="grid gap-6 md:grid-cols-2 print:grid-cols-1">
                <Card className="print:border-2 print:border-re-border-strong">
                    <CardHeader>
                        <div className="min-w-0">
                            <CardTitle>Cryptographic Timeline</CardTitle>
                            <CardDescription className="mt-1">
                                Simulated example — not a verification record
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <ol className="space-y-6">
                            {steps.map((step, i) => {
                                const StepIcon = step.icon;
                                const isComplete = step.status === 'complete';
                                return (
                                    <li key={i} className="flex items-start gap-3">
                                        <span
                                            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${isComplete
                                                ? 'border-re-text-primary bg-re-text-primary text-re-surface-card'
                                                : 'border-re-border text-re-text-tertiary'
                                                }`}
                                        >
                                            <StepIcon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                        </span>
                                        <div className="min-w-0 flex-1">
                                            <div className="mb-1 flex items-center justify-between gap-3">
                                                <h3 className="text-subheading text-re-text-primary">{step.title}</h3>
                                                <span className="shrink-0 font-mono text-small text-re-text-tertiary">{step.time}</span>
                                            </div>
                                            <div className="flex items-center gap-2 rounded-md border border-re-border-subtle bg-re-surface-inset px-2 py-1.5 font-mono text-[0.8125rem] text-re-text-secondary">
                                                <Lock className="h-3.5 w-3.5 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                                {step.hash}
                                            </div>
                                        </div>
                                    </li>
                                );
                            })}
                        </ol>
                    </CardContent>
                </Card>

                <div className="space-y-6">
                    <Card>
                        <CardHeader><CardTitle>Risk Details</CardTitle></CardHeader>
                        <CardContent className="space-y-3">
                            {data.critical_risks.map(risk => (
                                <Callout key={risk.id} tone="danger" title={<>{risk.severity} • {risk.id}</>}>
                                    {risk.description}
                                </Callout>
                            ))}
                            {data.critical_risks.length === 0 && (
                                <Callout tone="success">
                                    No Critical Risks Detected
                                </Callout>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>
        </PageContainer>
    );
}
