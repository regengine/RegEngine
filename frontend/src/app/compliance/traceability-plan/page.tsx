import Link from 'next/link';
import { Clock, FileText, ShieldCheck } from 'lucide-react';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export default function TraceabilityPlanPage() {
    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <PageContainer>
                <div className="max-w-3xl mx-auto py-12">
                    <div className="flex items-center gap-4 mb-8">
                        <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
                            <FileText className="h-8 w-8 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div>
                            <h1 className="text-4xl font-bold">Traceability Plan</h1>
                            <p className="text-muted-foreground mt-1">
                                FSMA 204 traceability plan workflow
                            </p>
                        </div>
                    </div>

                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <CardTitle>Coming Soon</CardTitle>
                                <Badge variant="secondary" className="gap-1">
                                    <Clock className="h-3.5 w-3.5" />
                                    In Development
                                </Badge>
                            </div>
                            <CardDescription>
                                This section is not yet connected to current tenant traceability-plan records.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="p-4 rounded-lg border bg-muted/40">
                                <div className="flex items-start gap-3">
                                    <ShieldCheck className="h-5 w-5 text-primary mt-0.5" />
                                    <p className="text-sm text-muted-foreground">
                                        To avoid presenting placeholder compliance data in production, this page is currently read-only.
                                        We will enable full plan management once the backend API integration is complete.
                                    </p>
                                </div>
                            </div>

                            <p className="text-sm text-muted-foreground">
                                For active compliance tracking, continue in{' '}
                                <Link href="/dashboard/compliance" className="text-primary font-medium hover:underline">
                                    Compliance Dashboard
                                </Link>
                                .
                            </p>
                        </CardContent>
                    </Card>
                </div>
            </PageContainer>
        </div>
    );
}
