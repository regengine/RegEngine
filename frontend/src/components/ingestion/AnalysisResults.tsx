import { AnalysisSummary } from '@/types/api';
import { AlertTriangle, CheckCircle, FileText, Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

interface AnalysisResultsProps {
    data: AnalysisSummary;
    onClose: () => void;
}

export function AnalysisResults({ data, onClose }: AnalysisResultsProps) {
    const getRiskColor = (score: number) => {
        if (score > 80) return 'text-re-danger bg-re-danger-muted border-re-danger';
        if (score > 50) return 'text-orange-600 bg-orange-50 border-orange-200';
        return 'text-re-success bg-re-success-muted border-green-200';
    };

    return (
        <div className="space-y-6 py-2">
            <div className="text-center space-y-2">
                <div className="inline-flex items-center justify-center p-3 rounded-full bg-re-success-muted mb-2">
                    <CheckCircle className="h-8 w-8 text-re-success" />
                </div>
                <h3 className="text-lg font-medium">Ingestion Complete</h3>
                <p className="text-sm text-muted-foreground">
                    We've analyzed your document and found the following insights.
                </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className={`p-4 rounded-lg border ${getRiskColor(data.risk_score)}`}>
                    <div className="text-sm font-medium opacity-80">Risk Score</div>
                    <div className="text-2xl font-bold">{data.risk_score}/100</div>
                </div>
                <div className="p-4 rounded-lg border bg-slate-50">
                    <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground mb-1">
                        <FileText className="h-4 w-4" /> Obligations
                    </div>
                    <div className="text-2xl font-bold">{data.obligations_count}</div>
                </div>
            </div>

            {data.critical_risks.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-sm font-medium flex items-center gap-2">
                        <AlertTriangle className="h-4 w-4 text-re-warning" />
                        Critical Attention Needed
                    </h4>
                    <div className="space-y-2">
                        {data.critical_risks.map((risk) => (
                            <div key={risk.id} className="text-sm p-3 bg-re-warning-muted text-re-warning rounded border border-re-warning">
                                {risk.description}
                            </div>
                        ))}
                    </div>
                </div>
            )}

            <div className="flex gap-3 pt-2">
                <Button variant="outline" onClick={onClose} className="flex-1">
                    Dismiss
                </Button>
                <Button className="flex-1" asChild>
                    <Link href={`/ingest/results/${data.document_id}`}>
                        View Full Report
                    </Link>
                </Button>
            </div>
        </div>
    );
}
