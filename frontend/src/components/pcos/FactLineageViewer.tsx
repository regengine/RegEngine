'use client';

import React, { useState } from 'react';

/**
 * FactLineageViewer - Visualizes the Authority & Fact Data Lineage flow
 * 
 * Shows the 4-step traceability chain:
 * 1. Authority Source → 2. Extracted Fact → 3. Context & Rule → 4. Audit Verdict
 */

interface AuthorityDocument {
    id: string;
    document_code: string;
    document_name: string;
    issuer: string;
    document_hash?: string;
    effective_date?: string;
}

interface ExtractedFact {
    id: string;
    fact_key: string;
    fact_name: string;
    version: number;
    source_quote?: string;
}

interface Provenance {
    authority_id: string;
    authority_code: string;
    authority_name: string;
    issuer: string;
    document_hash?: string;
    source_page?: number;
    source_section?: string;
    source_quote?: string;
}

interface LineageItem {
    citation_id: string;
    citation_type: string;
    evaluation_result: 'pass' | 'fail' | 'warning' | 'info';
    input_value?: string;
    fact_value_used: string;
    comparison_operator?: string;
    context_applied?: Record<string, unknown>;
    fact: ExtractedFact;
    authority: AuthorityDocument;
    cited_at: string;
}

interface VerdictLineageProps {
    entityType: string;
    entityId: string;
    lineage: LineageItem[];
    totalCitations: number;
}

interface FactLineageViewerProps {
    verdictLineage?: VerdictLineageProps;
    onLoadLineage?: (entityType: string, entityId: string) => void;
}

// Color mapping for evaluation results
const resultColors = {
    pass: { bg: 'bg-green-50', border: 'border-green-500', text: 'text-green-700', badge: 'bg-green-100 text-green-800' },
    fail: { bg: 'bg-red-50', border: 'border-red-500', text: 'text-red-700', badge: 'bg-red-100 text-red-800' },
    warning: { bg: 'bg-yellow-50', border: 'border-yellow-500', text: 'text-yellow-700', badge: 'bg-yellow-100 text-yellow-800' },
    info: { bg: 'bg-blue-50', border: 'border-blue-500', text: 'text-blue-700', badge: 'bg-blue-100 text-blue-800' },
};

export default function FactLineageViewer({ verdictLineage, onLoadLineage }: FactLineageViewerProps) {
    const [selectedItem, setSelectedItem] = useState<LineageItem | null>(null);
    const [expandedCards, setExpandedCards] = useState<Set<string>>(new Set());

    const toggleCard = (id: string) => {
        const newExpanded = new Set(expandedCards);
        if (newExpanded.has(id)) {
            newExpanded.delete(id);
        } else {
            newExpanded.add(id);
        }
        setExpandedCards(newExpanded);
    };

    // Demo data for when no lineage is provided
    const demoLineage: LineageItem = {
        citation_id: 'demo-1',
        citation_type: 'rate_comparison',
        evaluation_result: 'fail',
        input_value: '$1,000',
        fact_value_used: '$1,246',
        comparison_operator: 'gte',
        context_applied: { budget: 5000000, date: '2025-08-01' },
        fact: {
            id: 'fact-1',
            fact_key: 'SAG_MIN_DAY_RATE',
            fact_name: 'SAG Minimum Day Rate',
            version: 1,
            source_quote: 'Day players shall be paid at least $1,246 per day for productions over $2M budget.',
        },
        authority: {
            id: 'auth-1',
            document_code: 'SAG_CBA_2023',
            document_name: 'SAG-AFTRA Theatrical and Television Basic Agreement 2023-2026',
            issuer: 'SAG-AFTRA',
            document_hash: '8a7f2c3d...9e2b',
            effective_date: '2023-07-01',
        },
        cited_at: new Date().toISOString(),
    };

    const displayLineage = verdictLineage?.lineage || [demoLineage];

    return (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Authority & Fact Lineage</h3>
                    <p className="text-sm text-gray-500 mt-1">
                        Traceability chain from source documents to compliance verdicts
                    </p>
                </div>
                <span className="text-xs font-mono bg-blue-100 text-blue-800 px-3 py-1 rounded-full">
                    v1.0 Architecture
                </span>
            </div>

            {/* Lineage Flow */}
            <div className="space-y-6">
                {displayLineage.map((item, index) => (
                    <div key={item.citation_id} className="relative">
                        {/* Connection Line */}
                        {index > 0 && (
                            <div className="absolute -top-3 left-1/2 transform -translate-x-1/2 h-3 border-l-2 border-dashed border-gray-300" />
                        )}

                        {/* 4-Column Flow */}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">

                            {/* 1. Authority Source */}
                            <div
                                className="bg-gray-50 border border-gray-200 border-l-4 border-l-purple-500 rounded-lg p-4 cursor-pointer hover:shadow-md transition-shadow"
                                onClick={() => toggleCard(`auth-${item.citation_id}`)}
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-bold text-purple-700 uppercase tracking-wide">
                                        1. Authority
                                    </span>
                                    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                    </svg>
                                </div>
                                <p className="text-sm font-medium text-gray-900 truncate">{item.authority.document_code}</p>
                                <p className="text-xs text-gray-600 mt-1">{item.authority.issuer}</p>
                                {item.authority.effective_date && (
                                    <p className="text-xs text-gray-500 mt-1">Eff: {item.authority.effective_date}</p>
                                )}
                                {expandedCards.has(`auth-${item.citation_id}`) && item.authority.document_hash && (
                                    <div className="mt-3 pt-3 border-t border-gray-200">
                                        <p className="text-xs text-gray-500">Hash: {item.authority.document_hash}</p>
                                    </div>
                                )}
                            </div>

                            {/* 2. Extracted Fact */}
                            <div
                                className="bg-gray-50 border border-gray-200 border-l-4 border-l-blue-500 rounded-lg p-4 cursor-pointer hover:shadow-md transition-shadow"
                                onClick={() => toggleCard(`fact-${item.citation_id}`)}
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-bold text-blue-700 uppercase tracking-wide">
                                        2. Extracted Fact
                                    </span>
                                    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                    </svg>
                                </div>
                                <p className="text-sm font-medium text-gray-900">{item.fact.fact_key}</p>
                                <p className="bg-yellow-50 text-yellow-800 px-2 py-1 rounded text-sm mt-2 font-mono">
                                    {item.fact_value_used}
                                </p>
                                <p className="text-xs text-gray-500 mt-1">v{item.fact.version}</p>
                                {expandedCards.has(`fact-${item.citation_id}`) && item.fact.source_quote && (
                                    <div className="mt-3 pt-3 border-t border-gray-200">
                                        <p className="text-xs text-gray-600 italic">"{item.fact.source_quote}"</p>
                                    </div>
                                )}
                            </div>

                            {/* 3. Context & Rule */}
                            <div className="bg-gray-50 border border-gray-200 border-l-4 border-l-green-500 rounded-lg p-4">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs font-bold text-green-700 uppercase tracking-wide">
                                        3. Context & Rule
                                    </span>
                                    <svg className="h-4 w-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                    </svg>
                                </div>
                                <div className="text-xs font-mono text-gray-600 space-y-1">
                                    {item.context_applied && Object.entries(item.context_applied).map(([key, value]) => (
                                        <p key={key}>
                                            <span className="text-gray-400">{key}:</span> {String(value)}
                                        </p>
                                    ))}
                                </div>
                                <div className="mt-3 pt-2 border-t border-gray-200">
                                    <p className="text-[10px] text-gray-500 font-mono">
                                        {item.input_value} {item.comparison_operator || 'vs'} {item.fact_value_used}
                                    </p>
                                </div>
                            </div>

                            {/* 4. Audit Verdict */}
                            <div className={`${resultColors[item.evaluation_result].bg} border ${resultColors[item.evaluation_result].border} border-l-4 rounded-lg p-4`}>
                                <div className="mb-2">
                                    <span className={`text-xs font-bold uppercase tracking-wide ${resultColors[item.evaluation_result].text}`}>
                                        4. Audit Verdict
                                    </span>
                                </div>
                                <span className={`inline-block px-2 py-1 rounded text-xs font-bold uppercase ${resultColors[item.evaluation_result].badge}`}>
                                    {item.evaluation_result}
                                </span>
                                <div className="mt-3 text-xs text-gray-600 space-y-1">
                                    <p>Input: <span className="font-mono">{item.input_value}</span></p>
                                    <p>Required: <span className="font-mono">{item.fact_value_used}</span></p>
                                </div>
                                <p className="text-[10px] text-gray-400 mt-3">
                                    Citation: [{item.authority.document_code}]
                                </p>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Footer */}
            <div className="mt-6 pt-4 border-t border-gray-200">
                <p className="text-sm text-gray-600">
                    <strong>Figure: The Traceability Moat.</strong> Unlike standard calculators, this engine creates
                    a cryptographic link between the original PDF authority and the final audit verdict.
                </p>
                {verdictLineage && (
                    <p className="text-xs text-gray-500 mt-2">
                        Total citations: {verdictLineage.totalCitations} |
                        Entity: {verdictLineage.entityType}/{verdictLineage.entityId.substring(0, 8)}...
                    </p>
                )}
            </div>
        </div>
    );
}
