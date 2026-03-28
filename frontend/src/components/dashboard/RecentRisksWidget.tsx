'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, ChevronRight, FileText } from 'lucide-react';
import Link from 'next/link';

export function RecentRisksWidget() {
    // Mock data for demo (since backend might be cold)
    const risks = [
        { id: 'RISK-PHI-001', doc: 'Patient_Intake_Form_v2.pdf', score: 95, type: 'CRITICAL', desc: 'Unredacted PHI (SSN) detected' },
        { id: 'RISK-REG-002', doc: 'Q4_Financials.xlsx', score: 82, type: 'HIGH', desc: 'Missing SOX 404 Control Signature' },
        { id: 'RISK-EXP-003', doc: 'Turbine_Maint_Log.pdf', score: 65, type: 'MEDIUM', desc: 'Expired Maintenance Certificate' },
    ];

    return (
        <Card className="border-red-200 dark:border-red-900 bg-red-50/10 dark:bg-red-900/10">
            <CardHeader>
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-red-600 dark:text-red-400">
                        <AlertTriangle className="h-5 w-5" />
                        Recently Detected Risks
                    </CardTitle>
                    <Link href="/compliance/status" className="text-sm text-muted-foreground hover:underline">
                        View All
                    </Link>
                </div>
                <CardDescription>
                    Critical issues requiring immediate attention
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="space-y-4">
                    {risks.map((risk, i) => (
                        <div key={i} className="flex items-start justify-between p-3 bg-background rounded-lg border shadow-sm hover:shadow-md transition-all cursor-pointer group">
                            <div className="flex gap-3">
                                <FileText className="h-5 w-5 text-muted-foreground mt-1" />
                                <div>
                                    <div className="font-semibold text-sm group-hover:text-primary transition-colors">{risk.desc}</div>
                                    <div className="text-xs text-muted-foreground flex gap-2">
                                        <span>{risk.doc}</span>
                                        <span>•</span>
                                        <span className="font-mono">{risk.id}</span>
                                    </div>
                                </div>
                            </div>
                            <Badge variant={risk.score > 90 ? "destructive" : "secondary"}>
                                Score: {risk.score}
                            </Badge>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}
