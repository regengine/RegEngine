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
import { jsPDF } from 'jspdf';
import autoTable from 'jspdf-autotable';
import ExcelJS from 'exceljs';

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
            const doc = new jsPDF();
            let yPosition = 20;

            // Title
            doc.setFontSize(20);
            doc.text(data.title, 20, yPosition);
            yPosition += 10;

            // Subtitle
            if (data.subtitle) {
                doc.setFontSize(12);
                doc.setTextColor(100, 100, 100);
                doc.text(data.subtitle, 20, yPosition);
                yPosition += 10;
            }

            // Generated Date
            doc.setFontSize(10);
            doc.text(`Generated: ${new Date().toLocaleString()}`, 20, yPosition);
            yPosition += 15;

            // Metrics
            if (data.metrics && data.metrics.length > 0) {
                doc.setFontSize(14);
                doc.setTextColor(0, 0, 0);
                doc.text('Key Metrics', 20, yPosition);
                yPosition += 10;

                const metricsData = data.metrics.map((m) => [
                    m.label,
                    String(m.value),
                    m.helpText || '',
                ]);

                autoTable(doc, {
                    startY: yPosition,
                    head: [['Metric', 'Value', 'Description']],
                    body: metricsData,
                    theme: 'grid',
                    headStyles: { fillColor: [66, 139, 202] },
                });

                yPosition = ((doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable).finalY + 15;
            }

            // Tables
            if (data.tables && data.tables.length > 0) {
                for (const table of data.tables) {
                    if (yPosition > 250) {
                        doc.addPage();
                        yPosition = 20;
                    }

                    doc.setFontSize(14);
                    doc.setTextColor(0, 0, 0);
                    doc.text(table.title, 20, yPosition);
                    yPosition += 8;

                    autoTable(doc, {
                        startY: yPosition,
                        head: [table.headers],
                        body: table.rows,
                        theme: 'striped',
                        headStyles: { fillColor: [66, 139, 202] },
                    });

                    yPosition = ((doc as unknown as { lastAutoTable: { finalY: number } }).lastAutoTable).finalY + 15;
                }
            }

            // Metadata footer
            if (data.metadata) {
                const pageCount = doc.getNumberOfPages();
                for (let i = 1; i <= pageCount; i++) {
                    doc.setPage(i);
                    doc.setFontSize(8);
                    doc.setTextColor(150, 150, 150);
                    doc.text(
                        `RegEngine Compliance Report - Page ${i} of ${pageCount}`,
                        20,
                        285
                    );
                }
            }

            doc.save(`${sanitizeFilename(filename)}.pdf`);
        } catch (error) {
            console.error('PDF export failed:', error);
        } finally {
            setIsExporting(false);
        }
    };

    const exportToExcel = async () => {
        try {
            setIsExporting(true);
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
