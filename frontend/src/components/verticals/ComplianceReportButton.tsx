'use client';

import React, { useCallback, useState } from 'react';
import { Button } from '@/components/ui/button';
import { FileDown, Loader2, CheckCircle } from 'lucide-react';
import { generateBrandedPDF, type PDFSection } from '@/lib/pdf-report';

interface ComplianceReportButtonProps {
    /** Dashboard title used as the report header */
    dashboardTitle: string;
    /** Industry vertical (e.g. "Food Safety", "Energy", "Healthcare") */
    vertical: string;
    /** Optional tenant name for the report header */
    tenantName?: string;
    /** Additional data to include in the report */
    reportData?: {
        metrics?: Array<{ label: string; value: string | number; status?: 'pass' | 'fail' | 'warning' }>;
        alerts?: Array<{ severity: string; message: string; timestamp?: string }>;
        summary?: string;
    };
    className?: string;
}

/**
 * Generates a print-friendly HTML compliance report and triggers download.
 */
export function ComplianceReportButton({
    dashboardTitle,
    vertical,
    tenantName,
    reportData,
    className = '',
}: ComplianceReportButtonProps) {
    const [state, setState] = useState<'idle' | 'generating' | 'done'>('idle');

    const generateReport = useCallback(() => {
        setState('generating');

        // Small delay for UX feedback
        setTimeout(() => {
            const now = new Date();
            const timestamp = now.toISOString().split('T')[0];

            const sections: PDFSection[] = [
                { type: 'heading', text: 'Report Context', level: 2 },
                {
                    type: 'keyValue',
                    pairs: [
                        { key: 'Vertical', value: vertical },
                        { key: 'Tenant', value: tenantName || 'N/A' },
                        { key: 'Generated At', value: now.toLocaleString() },
                    ],
                },
            ];

            if (reportData?.summary) {
                sections.push({ type: 'divider' });
                sections.push({ type: 'heading', text: 'Executive Summary', level: 2 });
                sections.push({ type: 'text', body: reportData.summary });
            }

            if (reportData?.metrics && reportData.metrics.length > 0) {
                sections.push({ type: 'divider' });
                sections.push({ type: 'heading', text: 'Compliance Metrics', level: 2 });
                sections.push({
                    type: 'keyValue',
                    pairs: reportData.metrics.map((metric) => ({
                        key: metric.label,
                        value: String(metric.value),
                        status:
                            metric.status === 'pass'
                                ? 'success'
                                : metric.status === 'fail'
                                    ? 'danger'
                                    : metric.status === 'warning'
                                        ? 'warning'
                                        : 'neutral',
                    })),
                });
            }

            if (reportData?.alerts && reportData.alerts.length > 0) {
                sections.push({ type: 'divider' });
                sections.push({ type: 'heading', text: 'Active Alerts', level: 2 });
                sections.push({
                    type: 'table',
                    headers: ['Severity', 'Description', 'Timestamp'],
                    rows: reportData.alerts.map((alert) => [
                        alert.severity.toUpperCase(),
                        alert.message,
                        alert.timestamp || '-',
                    ]),
                });
            }

            generateBrandedPDF({
                title: dashboardTitle,
                subtitle: `${vertical} Compliance Report`,
                reportType: `${vertical} Dashboard Compliance`,
                sections,
                footer: {
                    left: 'Confidential',
                    right: 'regengine.co',
                    legalLine: 'Generated automatically from dashboard data',
                },
                filename: `compliance-report-${vertical.toLowerCase().replace(/\s+/g, '-')}-${timestamp}`,
            });

            setState('done');
            setTimeout(() => setState('idle'), 2000);
        }, 600);
    }, [dashboardTitle, vertical, tenantName, reportData]);

    return (
        <Button
            variant="outline"
            size="sm"
            onClick={generateReport}
            disabled={state === 'generating'}
            className={`gap-2 ${className}`}
        >
            {state === 'generating' && <Loader2 className="h-4 w-4 animate-spin" />}
            {state === 'done' && <CheckCircle className="h-4 w-4 text-emerald-500" />}
            {state === 'idle' && <FileDown className="h-4 w-4" />}
            {state === 'generating' ? 'Generating…' : state === 'done' ? 'Downloaded' : 'Export Report'}
        </Button>
    );
}
