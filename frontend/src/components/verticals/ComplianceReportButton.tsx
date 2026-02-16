'use client';

import React, { useCallback, useState } from 'react';
import { Button } from '@/components/ui/button';
import { FileDown, Loader2, CheckCircle } from 'lucide-react';

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
            const timeStr = now.toLocaleTimeString();

            const statusColor = (s?: string) => {
                if (s === 'pass') return '#10b981';
                if (s === 'fail') return '#ef4444';
                if (s === 'warning') return '#f59e0b';
                return '#6b7280';
            };

            const metricsRows = (reportData?.metrics || [])
                .map(
                    (m) => `
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">${m.label}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-weight:600;">${m.value}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">
            <span style="color:${statusColor(m.status)};font-weight:600;">
              ${m.status ? m.status.toUpperCase() : '—'}
            </span>
          </td>
        </tr>`
                )
                .join('');

            const alertRows = (reportData?.alerts || [])
                .map(
                    (a) => `
        <tr>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">
            <span style="color:${a.severity === 'critical' ? '#ef4444' : a.severity === 'warning' ? '#f59e0b' : '#6b7280'};font-weight:600;">
              ${a.severity.toUpperCase()}
            </span>
          </td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">${a.message}</td>
          <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">${a.timestamp || '—'}</td>
        </tr>`
                )
                .join('');

            const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${dashboardTitle} — Compliance Report</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #1f2937; padding: 40px; max-width: 800px; margin: 0 auto; }
    .header { border-bottom: 3px solid #10b981; padding-bottom: 16px; margin-bottom: 32px; }
    .header h1 { font-size: 24px; color: #111827; }
    .header .meta { color: #6b7280; font-size: 13px; margin-top: 4px; }
    .section { margin-bottom: 32px; }
    .section h2 { font-size: 16px; color: #374151; margin-bottom: 12px; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th { text-align: left; padding: 8px 12px; background: #f9fafb; border-bottom: 2px solid #e5e7eb; font-weight: 600; color: #374151; }
    .footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; }
    @media print { body { padding: 20px; } }
  </style>
</head>
<body>
  <div class="header">
    <h1>${dashboardTitle}</h1>
    <div class="meta">
      Vertical: ${vertical} · ${tenantName ? `Tenant: ${tenantName} · ` : ''}Generated: ${timestamp} ${timeStr}
    </div>
  </div>

  ${reportData?.summary ? `<div class="section"><h2>Executive Summary</h2><p style="font-size:14px;line-height:1.6;color:#4b5563;">${reportData.summary}</p></div>` : ''}

  ${metricsRows ? `
  <div class="section">
    <h2>Compliance Metrics</h2>
    <table>
      <thead><tr><th>Metric</th><th>Value</th><th>Status</th></tr></thead>
      <tbody>${metricsRows}</tbody>
    </table>
  </div>` : ''}

  ${alertRows ? `
  <div class="section">
    <h2>Active Alerts</h2>
    <table>
      <thead><tr><th>Severity</th><th>Description</th><th>Timestamp</th></tr></thead>
      <tbody>${alertRows}</tbody>
    </table>
  </div>` : ''}

  <div class="footer">
    <p>RegEngine Compliance Report · Confidential · Generated automatically from dashboard data</p>
    <p>This report is a point-in-time snapshot. Verify current compliance status in the live dashboard.</p>
  </div>
</body>
</html>`;

            // Trigger download
            const blob = new Blob([html], { type: 'text/html' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `compliance-report-${vertical.toLowerCase().replace(/\s+/g, '-')}-${timestamp}.html`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

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
