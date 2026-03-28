/**
 * Export Button Component
 * 
 * Provides PDF, Excel, and CSV export functionality for dashboard data.
 * Reusable across all vertical dashboards.
 */

'use client';

import React, { useState } from 'react';
import { Download, FileText, FileSpreadsheet, File } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { generateBrandedPDF, type PDFSection } from '@/lib/pdf-report';

export interface ExportData {
    title: string;
    subtitle?: string;
    metrics?: Array<{
        label: string;
        value: string | number;
        helpText?: string;
    }>;
    tables?: Array<{
        title: string;
        headers: string[];
        rows: (string | number)[][];
    }>;
    metadata?: Record<string, string | number>;
}

interface ExportButtonProps {
    data: ExportData;
    filename?: string;
    variant?: 'default' | 'outline' | 'ghost';
    size?: 'default' | 'sm' | 'lg';
    className?: string;
}

export function ExportButton({
    data,
    filename = 'compliance-report',
    variant = 'outline',
    size = 'default',
    className,
}: ExportButtonProps) {
    const [isExporting, setIsExporting] = useState(false);

    const sanitizeFilename = (name: string) => {
        return name.replace(/[^a-z0-9]/gi, '_').toLowerCase();
    };

    const exportToPDF = async () => {
        try {
            setIsExporting(true);

            const sections: PDFSection[] = [];

            if (data.metrics && data.metrics.length > 0) {
                sections.push({ type: 'heading', text: 'Key Metrics', level: 2 });
                sections.push({
                    type: 'table',
                    headers: ['Metric', 'Value', 'Description'],
                    rows: data.metrics.map((metric) => [
                        metric.label,
                        String(metric.value),
                        metric.helpText || '-',
                    ]),
                });
            }

            if (data.tables && data.tables.length > 0) {
                data.tables.forEach((table) => {
                    sections.push({ type: 'heading', text: table.title, level: 2 });
                    sections.push({
                        type: 'table',
                        headers: table.headers,
                        rows: table.rows.map((row) => row.map((cell) => String(cell))),
                    });
                });
            }

            if (data.metadata && Object.keys(data.metadata).length > 0) {
                sections.push({ type: 'heading', text: 'Metadata', level: 2 });
                sections.push({
                    type: 'keyValue',
                    pairs: Object.entries(data.metadata).map(([key, value]) => ({
                        key,
                        value: String(value),
                    })),
                });
            }

            await generateBrandedPDF({
                title: data.title,
                subtitle: data.subtitle,
                reportType: 'RegEngine Compliance Report',
                sections,
                footer: {
                    left: 'Confidential',
                    right: 'regengine.co',
                    legalLine: 'RegEngine Compliance Report',
                },
                filename: sanitizeFilename(filename),
            });
        } catch (error) {
            console.error('PDF export failed:', error);
        } finally {
            setIsExporting(false);
        }
    };

    const exportToExcel = async () => {
        try {
            setIsExporting(true);
            const ExcelJS = (await import('exceljs')).default;
            const workbook = new ExcelJS.Workbook();
            workbook.created = new Date();

            // Summary Sheet
            const summary = workbook.addWorksheet('Summary');
            summary.addRow([data.title]);
            if (data.subtitle) summary.addRow([data.subtitle]);
            summary.addRow([`Generated: ${new Date().toLocaleString()}`]);
            summary.addRow([]);

            if (data.metrics && data.metrics.length > 0) {
                summary.addRow(['Key Metrics']);
                summary.addRow(['Metric', 'Value', 'Description']);
                data.metrics.forEach((m) => {
                    summary.addRow([m.label, String(m.value), m.helpText || '']);
                });
            }

            // Table Sheets
            if (data.tables && data.tables.length > 0) {
                data.tables.forEach((table) => {
                    const sheetName = table.title.substring(0, 31); // Excel limit
                    const ws = workbook.addWorksheet(sheetName);
                    ws.addRow(table.headers);
                    table.rows.forEach((row) => ws.addRow(row));
                });
            }

            const buffer = await workbook.xlsx.writeBuffer();
            const blob = new Blob([buffer], {
                type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `${sanitizeFilename(filename)}.xlsx`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Excel export failed:', error);
        } finally {
            setIsExporting(false);
        }
    };

    const exportToCSV = async () => {
        try {
            setIsExporting(false);
            let csvContent = '';

            // Header
            csvContent += `"${data.title}"\n`;
            if (data.subtitle) {
                csvContent += `"${data.subtitle}"\n`;
            }
            csvContent += `"Generated: ${new Date().toLocaleString()}"\n\n`;

            // Metrics
            if (data.metrics && data.metrics.length > 0) {
                csvContent += '"Key Metrics"\n';
                csvContent += '"Metric","Value","Description"\n';
                data.metrics.forEach((m) => {
                    csvContent += `"${m.label}","${m.value}","${m.helpText || ''}"\n`;
                });
                csvContent += '\n';
            }

            // Tables
            if (data.tables && data.tables.length > 0) {
                data.tables.forEach((table) => {
                    csvContent += `\n"${table.title}"\n`;
                    csvContent += table.headers.map((h) => `"${h}"`).join(',') + '\n';
                    table.rows.forEach((row) => {
                        csvContent += row.map((cell) => `"${cell}"`).join(',') + '\n';
                    });
                });
            }

            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `${sanitizeFilename(filename)}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } catch (error) {
            console.error('CSV export failed:', error);
        } finally {
            setIsExporting(false);
        }
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    variant={variant}
                    size={size}
                    disabled={isExporting}
                    className={className}
                >
                    <Download className="w-4 h-4 mr-2" />
                    {isExporting ? 'Exporting...' : 'Export'}
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuLabel>Export Format</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={exportToPDF} disabled={isExporting}>
                    <FileText className="w-4 h-4 mr-2" />
                    Export as PDF
                </DropdownMenuItem>
                <DropdownMenuItem onClick={exportToExcel} disabled={isExporting}>
                    <FileSpreadsheet className="w-4 h-4 mr-2" />
                    Export as Excel
                </DropdownMenuItem>
                <DropdownMenuItem onClick={exportToCSV} disabled={isExporting}>
                    <File className="w-4 h-4 mr-2" />
                    Export as CSV
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
