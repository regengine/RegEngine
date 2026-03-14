'use client';

import React, { useState } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { BookOpen, FileText, Share2, Search, Link2, CheckCircle2 } from 'lucide-react';

interface ExtractedFact {
    id: string;
    type: 'Obligation' | 'Definition' | 'Threshold' | 'Exemption';
    title: string;
    description: string;
    confidence: number;
    highlightId: string;
}

const DEMO_TEXT = `
PART 1—GENERAL ENFORCEMENT REGULATIONS
Subpart S—Additional Traceability Records for Certain Foods

§ 1.1300 Who is subject to this subpart?
Except as specified in § 1.1305, the requirements of this subpart apply to persons who manufacture, process, pack, or hold foods that appear on the list of foods for which additional traceability records are required in accordance with section 204(d)(2) of the FDA Food Safety Modernization Act (Food Traceability List).

§ 1.1305 What foods and persons are exempt from this subpart?
(a) Exemptions for certain farms. (1) This subpart does not apply to a farm, or the farm's activities, with respect to produce that is completely packaged on the farm.
(2) This subpart does not apply to a farm, or the farm's activities, with respect to produce that is grown on a farm that had an average annual monetary value of produce sold during the previous 3-year period of no more than $25,000 (on a rolling basis), adjusted for inflation using 2011 as the baseline year for calculating the adjustment.

§ 1.1330 What records must I keep and provide when I receive a food on the Food Traceability List?
(a) General requirements. For each traceability lot of a food on the Food Traceability List you receive, you must maintain records containing the following information and linking this information to the traceability lot code for the food:
(1) The location description for the immediate previous source (other than a transporter) of the food;
(2) The location description for where the food was received;
(3) The date you received the food;
(4) The quantity and unit of measure of the food;
(5) The traceability lot code for the food;
(6) The location description for the traceability lot code source, or the traceability lot code source reference;
(7) The reference document type and reference document number.
`;

const DEMO_FACTS: ExtractedFact[] = [
    {
        id: 'f1',
        type: 'Obligation',
        title: 'Maintain receiving records',
        description: 'Must maintain records linking information to the traceability lot code when receiving food on the FTL.',
        confidence: 0.98,
        highlightId: 'h-1.1330-a',
    },
    {
        id: 'f2',
        type: 'Exemption',
        title: 'Small Farm Exemption',
        description: 'Farms with average annual produce sales under $25,000 (adjusted for inflation) are exempt.',
        confidence: 0.95,
        highlightId: 'h-1.1305-a-2',
    },
    {
        id: 'f3',
        type: 'Definition',
        title: 'Applicability Scope',
        description: 'Applies to persons who manufacture, process, pack, or hold foods on the Food Traceability List.',
        confidence: 0.99,
        highlightId: 'h-1.1300',
    }
];

interface ViewerProps {
    documentId: string;
}

export function NormalizedDocumentViewer({ documentId }: ViewerProps) {
    const [activeHighlight, setActiveHighlight] = useState<string | null>(null);

    const renderHighlightedText = () => {
        // In a real app, this would use exact string matching or AST node mapping
        // Here we split the text and conditionally wrap with spans based on simple matching
        const segments = [
            { id: 'none1', text: 'PART 1—GENERAL ENFORCEMENT REGULATIONS\nSubpart S—Additional Traceability Records for Certain Foods\n\n§ 1.1300 Who is subject to this subpart?\n' },
            { id: 'h-1.1300', text: 'Except as specified in § 1.1305, the requirements of this subpart apply to persons who manufacture, process, pack, or hold foods that appear on the list of foods for which additional traceability records are required in accordance with section 204(d)(2) of the FDA Food Safety Modernization Act (Food Traceability List).' },
            { id: 'none2', text: '\n\n§ 1.1305 What foods and persons are exempt from this subpart?\n(a) Exemptions for certain farms. (1) This subpart does not apply to a farm, or the farm\'s activities, with respect to produce that is completely packaged on the farm.\n' },
            { id: 'h-1.1305-a-2', text: '(2) This subpart does not apply to a farm, or the farm\'s activities, with respect to produce that is grown on a farm that had an average annual monetary value of produce sold during the previous 3-year period of no more than $25,000 (on a rolling basis), adjusted for inflation using 2011 as the baseline year for calculating the adjustment.' },
            { id: 'none3', text: '\n\n§ 1.1330 What records must I keep and provide when I receive a food on the Food Traceability List?\n' },
            { id: 'h-1.1330-a', text: '(a) General requirements. For each traceability lot of a food on the Food Traceability List you receive, you must maintain records containing the following information and linking this information to the traceability lot code for the food:\n(1) The location description for the immediate previous source (other than a transporter) of the food;\n(2) The location description for where the food was received;\n(3) The date you received the food;\n(4) The quantity and unit of measure of the food;\n(5) The traceability lot code for the food;\n(6) The location description for the traceability lot code source, or the traceability lot code source reference;\n(7) The reference document type and reference document number.' },
            { id: 'none4', text: '\n' }
        ];

        return segments.map((seg, i) => {
            if (seg.id.startsWith('none')) {
                return <span key={i} className="whitespace-pre-wrap">{seg.text}</span>;
            }

            const isHighlighted = activeHighlight === seg.id;

            return (
                <span
                    key={i}
                    id={seg.id}
                    className={`whitespace-pre-wrap transition-colors duration-300 rounded px-1 -mx-1 ${isHighlighted
                            ? 'bg-emerald-500/30 text-emerald-900 border-b-2 border-emerald-500 dark:bg-emerald-500/40 dark:text-emerald-50'
                            : 'hover:bg-slate-100 dark:hover:bg-slate-800 cursor-pointer'
                        }`}
                    onClick={() => setActiveHighlight(seg.id)}
                >
                    {seg.text}
                </span>
            );
        });
    };

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-[700px]">
            {/* Left Pane: Source Document */}
            <Card className="flex flex-col overflow-hidden border-slate-200 dark:border-slate-800">
                <div className="p-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-slate-500" />
                        <span className="font-mono text-xs font-semibold text-slate-600 dark:text-slate-300">
                            source_document.txt
                        </span>
                    </div>
                    <Badge variant="outline" className="text-[10px] uppercase font-mono">
                        ID: {documentId.substring(0, 8)}
                    </Badge>
                </div>
                <ScrollArea className="flex-1 p-6 bg-white dark:bg-[#0f1115]">
                    <div className="font-serif leading-loose text-slate-800 dark:text-slate-300 text-[15px] max-w-prose">
                        {renderHighlightedText()}
                    </div>
                </ScrollArea>
            </Card>

            {/* Right Pane: Extracted Facts */}
            <Card className="flex flex-col overflow-hidden border-emerald-200/50 dark:border-emerald-900/30 bg-emerald-50/30 dark:bg-emerald-950/10">
                <div className="p-3 border-b border-emerald-100 dark:border-emerald-900/50 bg-emerald-100/50 dark:bg-emerald-900/20 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <BookOpen className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                        <span className="font-mono text-xs font-semibold text-emerald-800 dark:text-emerald-300">
                            normalized_facts.json
                        </span>
                    </div>
                    <Badge className="bg-emerald-500 text-white hover:bg-emerald-600 text-[10px]">
                        {DEMO_FACTS.length} Extracted Items
                    </Badge>
                </div>

                <ScrollArea className="flex-1 p-4">
                    <div className="space-y-4">
                        {DEMO_FACTS.map((fact) => {
                            const isActive = activeHighlight === fact.highlightId;

                            return (
                                <div
                                    key={fact.id}
                                    className={`p-4 rounded-xl border transition-all cursor-pointer ${isActive
                                            ? 'border-emerald-400 bg-white dark:bg-slate-900 shadow-md transform scale-[1.02]'
                                            : 'border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-slate-900/50 hover:border-emerald-300'
                                        }`}
                                    onClick={() => {
                                        setActiveHighlight(fact.highlightId);
                                        // Scroll logic for the left pane
                                        const el = document.getElementById(fact.highlightId);
                                        if (el) {
                                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                        }
                                    }}
                                >
                                    <div className="flex items-center justify-between mb-2">
                                        <Badge variant="outline" className={`text-[10px] ${fact.type === 'Obligation' ? 'text-blue-500 border-blue-200 bg-blue-50 dark:bg-blue-950 dark:border-blue-900' :
                                                fact.type === 'Exemption' ? 'text-amber-500 border-amber-200 bg-amber-50 dark:bg-amber-950 dark:border-amber-900' :
                                                    'text-purple-500 border-purple-200 bg-purple-50 dark:bg-purple-950 dark:border-purple-900'
                                            }`}>
                                            {fact.type}
                                        </Badge>
                                        <div className="flex items-center gap-1 text-[10px] text-slate-400 font-mono">
                                            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                                            {(fact.confidence * 100).toFixed(0)}% Conf
                                        </div>
                                    </div>
                                    <h4 className="font-bold text-sm text-slate-900 dark:text-slate-100 mb-1">
                                        {fact.title}
                                    </h4>
                                    <p className="text-xs text-slate-600 dark:text-slate-400 mb-3">
                                        {fact.description}
                                    </p>

                                    <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-800">
                                        <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30 px-2 py-1 rounded">
                                            <Link2 className="h-3 w-3" />
                                            View Source Lineage
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </ScrollArea>
            </Card>
        </div>
    );
}
