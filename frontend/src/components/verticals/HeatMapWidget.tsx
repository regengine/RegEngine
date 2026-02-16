'use client';

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';

export interface HeatMapCell {
    value: number;  // 0-100 compliance percentage
    label?: string;
}

export interface HeatMapRow {
    category: string;
    cells: HeatMapCell[];
}

interface HeatMapWidgetProps {
    title: string;
    description?: string;
    rows: HeatMapRow[];
    columnLabels: string[];
    className?: string;
}

function getCellColor(value: number): string {
    if (value >= 90) return 'bg-emerald-500/80 dark:bg-emerald-500/60';
    if (value >= 70) return 'bg-emerald-500/40 dark:bg-emerald-500/30';
    if (value >= 50) return 'bg-amber-500/60 dark:bg-amber-500/40';
    if (value >= 30) return 'bg-amber-500/30 dark:bg-amber-500/20';
    if (value > 0) return 'bg-red-500/60 dark:bg-red-500/40';
    return 'bg-muted/30';
}

function getCellText(value: number): string {
    if (value >= 70) return 'text-white dark:text-white';
    if (value >= 50) return 'text-white dark:text-white';
    return 'text-foreground';
}

export function HeatMapWidget({ title, description, rows, columnLabels, className = '' }: HeatMapWidgetProps) {
    return (
        <Card className={className}>
            <CardHeader className="pb-3">
                <CardTitle className="text-base">{title}</CardTitle>
                {description && <CardDescription>{description}</CardDescription>}
            </CardHeader>
            <CardContent>
                <div className="overflow-x-auto">
                    <table className="w-full border-separate border-spacing-1">
                        <thead>
                            <tr>
                                <th className="text-left text-xs text-muted-foreground font-medium pb-2 pr-3 min-w-[120px]">
                                    Category
                                </th>
                                {columnLabels.map((label) => (
                                    <th
                                        key={label}
                                        className="text-center text-xs text-muted-foreground font-medium pb-2 min-w-[48px]"
                                    >
                                        {label}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((row) => (
                                <tr key={row.category}>
                                    <td className="text-xs font-medium pr-3 py-0.5 whitespace-nowrap">
                                        {row.category}
                                    </td>
                                    {row.cells.map((cell, ci) => (
                                        <td key={ci} className="p-0.5">
                                            <div
                                                className={`
                          w-full aspect-square min-w-[40px] min-h-[40px] rounded-md
                          flex items-center justify-center text-xs font-semibold
                          transition-all hover:scale-110 hover:shadow-lg cursor-default
                          ${getCellColor(cell.value)} ${getCellText(cell.value)}
                        `}
                                                title={`${row.category} · ${columnLabels[ci]}: ${cell.value}%`}
                                            >
                                                {cell.value > 0 ? `${cell.value}` : '—'}
                                            </div>
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Legend */}
                <div className="flex items-center gap-3 mt-4 pt-3 border-t">
                    <span className="text-xs text-muted-foreground">Legend:</span>
                    {[
                        { color: 'bg-emerald-500/80', label: '90-100%' },
                        { color: 'bg-emerald-500/40', label: '70-89%' },
                        { color: 'bg-amber-500/60', label: '50-69%' },
                        { color: 'bg-amber-500/30', label: '30-49%' },
                        { color: 'bg-red-500/60', label: '<30%' },
                    ].map(({ color, label }) => (
                        <div key={label} className="flex items-center gap-1">
                            <div className={`w-3 h-3 rounded-sm ${color}`} />
                            <span className="text-xs text-muted-foreground">{label}</span>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
}
