/**
 * Budget Analysis Component
 * 
 * Displays budget fringe analysis with visualizations for
 * union costs, payroll taxes, and shortfall detection.
 */

import React, { useState, useEffect } from 'react';

interface FringeBreakdown {
    line_item_id: string;
    description: string;
    labor_cost: number;
    union_code: string;
    union_fringe: number;
    statutory: number;
    workers_comp: number;
    total_burden: number;
    burden_pct: number;
}

interface FringeAnalysis {
    budget_id: string;
    budget_total: number;
    total_labor_cost: number;
    total_union_fringes: number;
    total_statutory_taxes: number;
    total_workers_comp: number;
    total_employer_burden: number;
    budgeted_fringes: number;
    budgeted_fringes_detected: number;
    shortfall: number;
    shortfall_pct: number;
    is_underfunded: boolean;
    warnings: string[];
    breakdown_by_item: FringeBreakdown[];
}

interface Props {
    budgetId: string;
}

const formatCurrency = (amt: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amt);

const formatPercent = (pct: number) => `${pct.toFixed(1)}%`;

export function BudgetAnalysis({ budgetId }: Props) {
    const [analysis, setAnalysis] = useState<FringeAnalysis | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showBreakdown, setShowBreakdown] = useState(false);

    useEffect(() => {
        loadAnalysis();
    }, [budgetId]);

    async function loadAnalysis() {
        try {
            setLoading(true);
            const response = await fetch(`/api/pcos/budgets/${budgetId}/fringe-analysis`);
            if (!response.ok) throw new Error('Failed to load fringe analysis');
            const data = await response.json();
            setAnalysis(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    }

    if (loading) {
        return (
            <div className="animate-pulse space-y-4">
                <div className="h-48 bg-slate-100 rounded-xl"></div>
            </div>
        );
    }

    if (error || !analysis) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
                <p className="font-medium">Error loading budget analysis</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    const burdenPct = analysis.total_labor_cost > 0
        ? (analysis.total_employer_burden / analysis.total_labor_cost * 100)
        : 0;

    return (
        <div className="space-y-6">
            {/* Shortfall Alert */}
            {analysis.is_underfunded && (
                <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg">
                    <div className="flex items-start gap-3">
                        <span className="text-red-500 text-2xl">⚠️</span>
                        <div>
                            <h3 className="font-semibold text-red-800">Fringe Shortfall Detected</h3>
                            <p className="text-red-700 mt-1">
                                Budget is <strong>{formatCurrency(analysis.shortfall)}</strong> short on fringes
                                ({formatPercent(analysis.shortfall_pct)} underfunded)
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* Summary Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-gradient-to-br from-slate-50 to-slate-100 rounded-xl p-4 border border-slate-200">
                    <div className="text-sm text-slate-500">Total Labor</div>
                    <div className="text-xl font-bold text-slate-900 mt-1">
                        {formatCurrency(analysis.total_labor_cost)}
                    </div>
                </div>

                <div className="bg-gradient-to-br from-indigo-50 to-indigo-100 rounded-xl p-4 border border-indigo-200">
                    <div className="text-sm text-indigo-600">Union Fringes</div>
                    <div className="text-xl font-bold text-indigo-900 mt-1">
                        {formatCurrency(analysis.total_union_fringes)}
                    </div>
                </div>

                <div className="bg-gradient-to-br from-amber-50 to-amber-100 rounded-xl p-4 border border-amber-200">
                    <div className="text-sm text-amber-600">Payroll Taxes</div>
                    <div className="text-xl font-bold text-amber-900 mt-1">
                        {formatCurrency(analysis.total_statutory_taxes)}
                    </div>
                </div>

                <div className="bg-gradient-to-br from-emerald-50 to-emerald-100 rounded-xl p-4 border border-emerald-200">
                    <div className="text-sm text-emerald-600">Workers Comp</div>
                    <div className="text-xl font-bold text-emerald-900 mt-1">
                        {formatCurrency(analysis.total_workers_comp)}
                    </div>
                </div>
            </div>

            {/* Burden Visualization */}
            <div className="bg-white rounded-xl border border-slate-200 p-6">
                <h3 className="text-lg font-semibold text-slate-900 mb-4">Employer Burden Breakdown</h3>

                <div className="flex items-center gap-6 mb-6">
                    <div className="text-center">
                        <div className="text-3xl font-bold text-slate-900">
                            {formatPercent(burdenPct)}
                        </div>
                        <div className="text-sm text-slate-500">Total Burden</div>
                    </div>

                    <div className="flex-1">
                        <div className="h-8 bg-slate-100 rounded-full overflow-hidden flex">
                            <div
                                className="h-full bg-indigo-500"
                                style={{ width: `${(analysis.total_union_fringes / analysis.total_employer_burden * 100)}%` }}
                                title="Union Fringes"
                            />
                            <div
                                className="h-full bg-amber-500"
                                style={{ width: `${(analysis.total_statutory_taxes / analysis.total_employer_burden * 100)}%` }}
                                title="Payroll Taxes"
                            />
                            <div
                                className="h-full bg-emerald-500"
                                style={{ width: `${(analysis.total_workers_comp / analysis.total_employer_burden * 100)}%` }}
                                title="Workers Comp"
                            />
                        </div>
                        <div className="flex justify-between mt-2 text-xs text-slate-500">
                            <span className="flex items-center gap-1">
                                <span className="w-3 h-3 rounded bg-indigo-500"></span>
                                Union ({formatPercent(analysis.total_union_fringes / analysis.total_employer_burden * 100)})
                            </span>
                            <span className="flex items-center gap-1">
                                <span className="w-3 h-3 rounded bg-amber-500"></span>
                                Taxes ({formatPercent(analysis.total_statutory_taxes / analysis.total_employer_burden * 100)})
                            </span>
                            <span className="flex items-center gap-1">
                                <span className="w-3 h-3 rounded bg-emerald-500"></span>
                                WC ({formatPercent(analysis.total_workers_comp / analysis.total_employer_burden * 100)})
                            </span>
                        </div>
                    </div>
                </div>

                {/* Budget vs Required */}
                <div className="bg-slate-50 rounded-lg p-4 mt-4">
                    <div className="flex justify-between items-center">
                        <div>
                            <div className="text-sm text-slate-500">Total Required</div>
                            <div className="text-lg font-semibold text-slate-900">
                                {formatCurrency(analysis.total_employer_burden)}
                            </div>
                        </div>
                        <div className="text-center">
                            <div className={`text-2xl font-bold ${analysis.is_underfunded ? 'text-red-600' : 'text-emerald-600'}`}>
                                {analysis.is_underfunded ? '−' : '✓'}
                            </div>
                        </div>
                        <div className="text-right">
                            <div className="text-sm text-slate-500">Budgeted</div>
                            <div className="text-lg font-semibold text-slate-900">
                                {formatCurrency(analysis.budgeted_fringes_detected)}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Warnings */}
            {analysis.warnings.length > 0 && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                    <h3 className="font-semibold text-amber-800 mb-2">⚠️ Warnings</h3>
                    <ul className="space-y-1">
                        {analysis.warnings.map((warning, i) => (
                            <li key={i} className="text-sm text-amber-700">• {warning}</li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Line Item Breakdown */}
            <div className="bg-white rounded-xl border border-slate-200">
                <button
                    onClick={() => setShowBreakdown(!showBreakdown)}
                    className="w-full flex items-center justify-between p-4 hover:bg-slate-50"
                >
                    <h3 className="font-semibold text-slate-900">Line Item Breakdown</h3>
                    <span className="text-slate-400">{showBreakdown ? '▲' : '▼'}</span>
                </button>

                {showBreakdown && (
                    <div className="border-t border-slate-200">
                        <table className="w-full text-sm">
                            <thead className="bg-slate-50">
                                <tr className="text-left text-slate-500">
                                    <th className="px-4 py-2">Description</th>
                                    <th className="px-4 py-2 text-right">Labor</th>
                                    <th className="px-4 py-2">Union</th>
                                    <th className="px-4 py-2 text-right">Fringe</th>
                                    <th className="px-4 py-2 text-right">Burden %</th>
                                </tr>
                            </thead>
                            <tbody>
                                {analysis.breakdown_by_item.slice(0, 20).map((item, i) => (
                                    <tr key={i} className="border-t border-slate-100 hover:bg-slate-50">
                                        <td className="px-4 py-2 font-medium text-slate-900">{item.description || 'Line item'}</td>
                                        <td className="px-4 py-2 text-right text-slate-700">{formatCurrency(item.labor_cost)}</td>
                                        <td className="px-4 py-2">
                                            <span className="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded text-xs">
                                                {item.union_code}
                                            </span>
                                        </td>
                                        <td className="px-4 py-2 text-right text-slate-700">{formatCurrency(item.total_burden)}</td>
                                        <td className="px-4 py-2 text-right">
                                            <span className={`font-medium ${item.burden_pct > 30 ? 'text-amber-600' : 'text-slate-700'}`}>
                                                {formatPercent(item.burden_pct)}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        {analysis.breakdown_by_item.length > 20 && (
                            <div className="px-4 py-2 text-sm text-slate-500 bg-slate-50 text-center">
                                Showing 20 of {analysis.breakdown_by_item.length} items
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

export default BudgetAnalysis;
