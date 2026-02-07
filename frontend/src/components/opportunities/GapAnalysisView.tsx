'use client';

import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { AlertTriangle, FileText, ExternalLink } from 'lucide-react';
import { motion } from 'framer-motion';

interface Gap {
    concept?: string;
    example_text?: string;
    citation?: string | {
        doc_id: string;
        start: number;
        end: number;
        source_url: string;
    };
    severity?: 'High' | 'Medium' | 'Low' | 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
    gap_type?: string;
}

interface GapAnalysisViewProps {
    gaps: Gap[];
    j1: string;
    j2: string;
}

export function GapAnalysisView({ gaps, j1, j2 }: GapAnalysisViewProps) {
    const getSourceUrl = (citation?: Gap['citation']) => {
        if (!citation) return null;
        if (typeof citation === 'string') return null; // Or parse URL if it is one
        return citation.source_url;
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                    Gap Analysis: {j1} vs {j2}
                </CardTitle>
                <CardDescription>
                    Detailed breakdown of regulatory requirements present in {j1} but missing or different in {j2}.
                </CardDescription>
            </CardHeader>
            <CardContent>
                <div className="rounded-md border">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="w-[200px]">Concept</TableHead>
                                <TableHead>Requirement Detail</TableHead>
                                <TableHead className="w-[150px]">Source</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {gaps.map((gap, index) => {
                                const sourceUrl = getSourceUrl(gap.citation);
                                return (
                                    <TableRow key={index}>
                                        <TableCell className="font-medium">
                                            <div className="flex flex-col gap-1">
                                                <span>{gap.concept || 'General Requirement'}</span>
                                                {/* Mock severity for demo visual if not present */}
                                                <Badge
                                                    variant="outline"
                                                    className={index % 2 === 0 ? "border-red-200 text-red-700 bg-red-50 w-fit" : "border-amber-200 text-amber-700 bg-amber-50 w-fit"}
                                                >
                                                    {gap.severity || (index % 2 === 0 ? "High Impact" : "Medium Impact")}
                                                </Badge>
                                            </div>
                                        </TableCell>
                                        <TableCell>
                                            <p className="text-sm text-muted-foreground">{gap.example_text || 'No details available'}</p>
                                        </TableCell>
                                        <TableCell>
                                            {sourceUrl ? (
                                                <a
                                                    href={sourceUrl}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="flex items-center gap-1 text-sm text-blue-600 hover:underline"
                                                >
                                                    <FileText className="h-3 w-3" />
                                                    View Source
                                                    <ExternalLink className="h-3 w-3" />
                                                </a>
                                            ) : (
                                                <span className="text-sm text-muted-foreground">
                                                    {typeof gap.citation === 'string' ? gap.citation : 'Internal Doc'}
                                                </span>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                )
                            })}
                        </TableBody>
                    </Table>
                </div>
            </CardContent>
        </Card>
    );
}
