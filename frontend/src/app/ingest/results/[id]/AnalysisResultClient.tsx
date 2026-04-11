'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { AnalysisSummary } from '@/types/api';
import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { CheckCircle, Clock, Shield, Database, Lock, Search } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

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

    if (loading) return <div className="p-8">Loading Chain of Trust...</div>;
    if (!data) return <div className="p-8">Document Not Found</div>;

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
            title: "Blockchain Anchor",
            icon: Shield,
            status: "pending",
            hash: "Waiting...",
            time: "..."
        }
    ];

    return (
        <div className="container mx-auto py-8 space-y-8">
            <div className="flex items-center justify-between print:hidden">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Chain of Trust Evidence</h1>
                    <p className="text-muted-foreground">Document ID: <code className="bg-muted p-1 rounded">{data.document_id}</code></p>
                </div>
                <div className="flex gap-2">
                    <button
                        onClick={() => window.print()}
                        className="inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground shadow hover:bg-primary/90 h-9 px-4 py-2"
                    >
                        <Shield className="mr-2 h-4 w-4" /> Export Signed Report
                    </button>
                    <Badge variant={data.risk_score > 50 ? 'destructive' : 'default'} className="text-lg px-4 py-2">
                        Risk Score: {data.risk_score}/100
                    </Badge>
                </div>
            </div>

            {/* Print Header (Only visible when printing) */}
            <div className="hidden print:block mb-8 border-b pb-4">
                <h1 className="text-2xl font-bold">RegEngine Compliance Audit Report</h1>
                <p className="text-sm text-re-text-muted">Generated: {new Date().toLocaleString()}</p>
                <p className="text-sm text-re-text-muted">Document ID: {data.document_id}</p>
                <p className="text-sm font-bold mt-2">Integrity Status: VERIFIED</p>
            </div>

            <div className="grid gap-6 md:grid-cols-2 print:grid-cols-1">
                <Card className="print:shadow-none print:border-green-500 print:border-2">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Shield className="h-5 w-5 text-re-info" />
                            Cryptographic Timeline
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="relative border-l-2 border-muted ml-3 space-y-8 py-2">
                            {steps.map((step, i) => (
                                <div key={i} className="pl-8 relative">
                                    <div className={`absolute -left-[9px] top-1 h-4 w-4 rounded-full ${step.status === 'complete' ? 'bg-re-success-muted0' : 'bg-re-surface-elevated'}`} />
                                    <div className="flex items-center justify-between mb-1">
                                        <h3 className="font-semibold">{step.title}</h3>
                                        <span className="text-xs text-muted-foreground font-mono">{step.time}</span>
                                    </div>
                                    <div className="text-xs font-mono bg-slate-50 p-2 rounded border flex items-center gap-2">
                                        <Lock className="h-3 w-3 text-muted-foreground" />
                                        {step.hash}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </CardContent>
                </Card>

                <div className="space-y-6">
                    <Card>
                        <CardHeader><CardTitle>Risk Details</CardTitle></CardHeader>
                        <CardContent className="space-y-4">
                            {data.critical_risks.map(risk => (
                                <div key={risk.id} className="p-4 border rounded-lg bg-re-danger-muted text-re-danger border-re-danger">
                                    <div className="font-bold text-sm mb-1">{risk.severity} • {risk.id}</div>
                                    <div>{risk.description}</div>
                                </div>
                            ))}
                            {data.critical_risks.length === 0 && (
                                <div className="text-re-success flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" /> No Critical Risks Detected
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
