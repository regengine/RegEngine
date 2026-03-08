'use client';

import { useState, useEffect, type SVGProps } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import { apiClient } from '@/lib/api-client';
import {
    ShieldCheck,
    Search,
    Trash2,
    CheckCircle,
    AlertTriangle,
    Globe,
    ExternalLink,
    RefreshCw,
    Clock
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';

interface DiscoveryItem {
    body: string;
    url: string;
    index: number;
}

export default function CurationDashboard() {
    const [items, setItems] = useState<DiscoveryItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [processing, setProcessing] = useState<number | null>(null);
    const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
    const { toast } = useToast();

    const fetchQueue = async () => {
        try {
            setLoading(true);
            const data = await apiClient.getDiscoveryQueue();
            setItems(data);
            setSelectedIndices(new Set()); // Clear selection on refresh
        } catch (error) {
            console.error('Failed to fetch discovery queue:', error);
            toast({
                title: 'Offline Error',
                description: 'Could not connect to the ingestion service. Please ensure the backend is running.',
                variant: 'destructive',
            });
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchQueue();
    }, []);

    const toggleSelect = (index: number) => {
        const next = new Set(selectedIndices);
        if (next.has(index)) {
            next.delete(index);
        } else {
            next.add(index);
        }
        setSelectedIndices(next);
    };

    const toggleSelectAll = () => {
        if (selectedIndices.size === items.length) {
            setSelectedIndices(new Set());
        } else {
            setSelectedIndices(new Set(items.map(i => i.index)));
        }
    };

    const handleBulkApprove = async () => {
        if (selectedIndices.size === 0) return;
        try {
            setLoading(true);
            const indices = Array.from(selectedIndices);
            await apiClient.bulkApproveDiscovery(indices);
            toast({
                title: 'Success',
                description: `Successfully approved and triggered scrape for ${indices.length} items.`,
            });
            fetchQueue();
        } catch (error) {
            toast({
                title: 'Bulk Action Failed',
                description: 'Failed to approve multiple items.',
                variant: 'destructive',
            });
        } finally {
            setLoading(false);
        }
    };

    const handleBulkReject = async () => {
        if (selectedIndices.size === 0) return;
        try {
            setLoading(true);
            const indices = Array.from(selectedIndices);
            await apiClient.bulkRejectDiscovery(indices);
            toast({
                title: 'Success',
                description: `Successfully rejected ${indices.length} items.`,
            });
            fetchQueue();
        } catch (error) {
            toast({
                title: 'Bulk Action Failed',
                description: 'Failed to reject multiple items.',
                variant: 'destructive',
            });
        } finally {
            setLoading(false);
        }
    };

    const handleApprove = async (index: number) => {
        try {
            setProcessing(index);
            await apiClient.approveDiscovery(index);
            toast({
                title: 'Success',
                description: 'Discovery approved and scrape triggered',
            });
            fetchQueue();
        } catch (error) {
            console.error('Approval failed:', error);
            toast({
                title: 'Error',
                description: 'Failed to approve discovery',
                variant: 'destructive',
            });
        } finally {
            setProcessing(null);
        }
    };

    const handleReject = async (index: number) => {
        try {
            setProcessing(index);
            await apiClient.rejectDiscovery(index);
            toast({
                title: 'Success',
                description: 'Discovery rejected',
            });
            fetchQueue();
        } catch (error) {
            console.error('Rejection failed:', error);
            toast({
                title: 'Error',
                description: 'Failed to reject discovery',
                variant: 'destructive',
            });
        } finally {
            setProcessing(null);
        }
    };

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950/50">
            <PageContainer>
                <div className="max-w-6xl mx-auto space-y-8">
                    {/* Header */}
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="flex items-center gap-4">
                            <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20">
                                <ShieldCheck className="h-8 w-8 text-indigo-500" />
                            </div>
                            <div>
                                <h1 className="text-3xl font-bold tracking-tight">Manual Discovery Curation</h1>
                                <p className="text-slate-500 dark:text-slate-400">
                                    Review and approve regulatory links disallowed by robots.txt or failing automated discovery.
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            <AnimatePresence>
                                {selectedIndices.size > 0 && (
                                    <motion.div
                                        initial={{ opacity: 0, x: 20 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        exit={{ opacity: 0, x: 20 }}
                                        className="flex items-center gap-2 bg-indigo-500/5 p-1 rounded-lg border border-indigo-500/10"
                                    >
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            className="text-red-500 hover:text-red-600 hover:bg-red-50"
                                            onClick={handleBulkReject}
                                        >
                                            <Trash2 className="h-4 w-4 mr-2" />
                                            Reject ({selectedIndices.size})
                                        </Button>
                                        <Button
                                            size="sm"
                                            className="bg-indigo-600 hover:bg-indigo-700 text-white"
                                            onClick={handleBulkApprove}
                                        >
                                            <CheckCircle className="h-4 w-4 mr-2" />
                                            Approve ({selectedIndices.size})
                                        </Button>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                            <Button
                                variant="outline"
                                onClick={fetchQueue}
                                disabled={loading}
                                className="gap-2"
                            >
                                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                                Refresh
                            </Button>
                        </div>
                    </div>

                    {/* Stats Bar */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <Card className="bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm border-slate-200 dark:border-slate-800">
                            <CardContent className="pt-6 flex items-center gap-4">
                                <div className="p-2 rounded-lg bg-blue-500/10">
                                    <Clock className="h-5 w-5 text-blue-500" />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-slate-500">Pending Review</p>
                                    <p className="text-2xl font-bold">{items.length}</p>
                                </div>
                            </CardContent>
                        </Card>
                        <Card className="bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm border-slate-200 dark:border-slate-800">
                            <CardContent className="pt-6 flex items-center gap-4">
                                <div className="p-2 rounded-lg bg-amber-500/10">
                                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-slate-500">High Risk Domains</p>
                                    <p className="text-2xl font-bold">
                                        {new Set(items.map(i => {
                                            try { return new URL(i.url).hostname; }
                                            catch (e) { return 'invalid-url'; }
                                        })).size}
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                        <Card className="bg-white/50 dark:bg-slate-900/50 backdrop-blur-sm border-slate-200 dark:border-slate-800">
                            <CardContent className="pt-6 flex items-center gap-4">
                                <div className="p-2 rounded-lg bg-emerald-500/10">
                                    <Globe className="h-5 w-5 text-emerald-500" />
                                </div>
                                <div>
                                    <p className="text-sm font-medium text-slate-500">Global Coverage</p>
                                    <p className="text-2xl font-bold">100+</p>
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Main Content */}
                    <Card className="border-slate-200 dark:border-slate-800 shadow-xl shadow-slate-200/20 dark:shadow-none overflow-hidden">
                        <CardHeader className="bg-white dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800 pb-4">
                            <CardTitle>Discovery Queue</CardTitle>
                            <CardDescription>Items in this list require human verification before being codified into the graph.</CardDescription>
                        </CardHeader>
                        <CardContent className="p-0">
                            {loading && items.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-24 text-slate-400">
                                    <Spinner size="lg" className="mb-4" />
                                    <p>Loading discovery queue...</p>
                                </div>
                            ) : items.length === 0 ? (
                                <div className="flex flex-col items-center justify-center py-24 text-slate-400 text-center">
                                    <div className="p-4 rounded-full bg-slate-50 dark:bg-slate-800/50 mb-4">
                                        <CheckCircle className="h-12 w-12 text-slate-300 dark:text-slate-700" />
                                    </div>
                                    <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-100">Queue is Clear</h3>
                                    <p className="max-w-xs mx-auto mt-2">All discovered regulatory links have been processed or cleared.</p>
                                </div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left border-collapse">
                                        <thead>
                                            <tr className="bg-slate-50 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 text-xs font-semibold uppercase tracking-wider">
                                                <th className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 w-12">
                                                    <input
                                                        type="checkbox"
                                                        className="rounded border-slate-300 dark:border-slate-700 h-4 w-4 accent-indigo-600"
                                                        checked={selectedIndices.size === items.length && items.length > 0}
                                                        onChange={toggleSelectAll}
                                                    />
                                                </th>
                                                <th className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">Source Body</th>
                                                <th className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">URL / Link</th>
                                                <th className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 text-right">Actions</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                                            <AnimatePresence mode="popLayout">
                                                {items.map((item) => (
                                                    <motion.tr
                                                        key={`${item.body}-${item.index}`}
                                                        initial={{ opacity: 0 }}
                                                        animate={{ opacity: 1 }}
                                                        exit={{ opacity: 0, x: -20 }}
                                                        className={`hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors group ${selectedIndices.has(item.index) ? 'bg-indigo-500/5 dark:bg-indigo-500/10' : ''}`}
                                                    >
                                                        <td className="px-6 py-4 align-top">
                                                            <input
                                                                type="checkbox"
                                                                className="rounded border-slate-300 dark:border-slate-700 h-4 w-4 accent-indigo-600"
                                                                checked={selectedIndices.has(item.index)}
                                                                onChange={() => toggleSelect(item.index)}
                                                            />
                                                        </td>
                                                        <td className="px-6 py-4 align-top">
                                                            <div className="flex flex-col gap-1">
                                                                <span className="font-bold text-slate-900 dark:text-slate-100">{item.body}</span>
                                                                <Badge variant="outline" className="w-fit text-[10px] h-4 uppercase tracking-tighter">DISCOVERED</Badge>
                                                            </div>
                                                        </td>
                                                        <td className="px-6 py-4 align-top">
                                                            <div className="flex flex-col gap-2">
                                                                <code className="text-xs text-indigo-600 dark:text-indigo-400 break-all bg-indigo-50/50 dark:bg-indigo-500/10 p-2 rounded border border-indigo-100 dark:border-indigo-500/20 max-w-lg">
                                                                    {item.url}
                                                                </code>
                                                                <a
                                                                    href={item.url}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    className="text-xs flex items-center gap-1 text-slate-400 hover:text-indigo-500 transition-colors w-fit"
                                                                >
                                                                    <ExternalLink className="h-3 w-3" />
                                                                    Verify Document Source
                                                                </a>
                                                            </div>
                                                        </td>
                                                        <td className="px-6 py-4 align-top text-right">
                                                            <div className="flex items-center justify-end gap-2">
                                                                <Button
                                                                    size="sm"
                                                                    variant="outline"
                                                                    className="text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20 border-slate-200 dark:border-slate-800 h-9 px-3"
                                                                    onClick={() => handleReject(item.index)}
                                                                    disabled={processing !== null}
                                                                >
                                                                    {processing === item.index ? <Spinner size="sm" /> : <Trash2 className="h-4 w-4" />}
                                                                </Button>
                                                                <Button
                                                                    size="sm"
                                                                    className="bg-indigo-600 hover:bg-indigo-700 text-white h-9 px-4 gap-2 font-medium"
                                                                    onClick={() => handleApprove(item.index)}
                                                                    disabled={processing !== null}
                                                                >
                                                                    {processing === item.index ? (
                                                                        <Spinner size="sm" />
                                                                    ) : (
                                                                        <>
                                                                            <Search className="h-4 w-4" />
                                                                            Approve
                                                                        </>
                                                                    )}
                                                                </Button>
                                                            </div>
                                                        </td>
                                                    </motion.tr>
                                                ))}
                                            </AnimatePresence>
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Guidance */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pb-12">
                        <div className="space-y-4">
                            <h3 className="text-lg font-semibold flex items-center gap-2">
                                <AlertTriangle className="h-5 w-5 text-amber-500" />
                                Curation Guidelines
                            </h3>
                            <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-3">
                                <li className="flex gap-2">
                                    <div className="mt-1.5 h-1 w-1 rounded-full bg-slate-400 shrink-0" />
                                    Verify the link leads to an official regulatory document or landing page before approval.
                                </li>
                                <li className="flex gap-2">
                                    <div className="mt-1.5 h-1 w-1 rounded-full bg-slate-400 shrink-0" />
                                    If the link is a direct download (PDF/DOCX), our parser will prioritize high-fidelity extraction.
                                </li>
                                <li className="flex gap-2">
                                    <div className="mt-1.5 h-1 w-1 rounded-full bg-slate-400 shrink-0" />
                                    Approval bypasses robots.txt checks. Only approve if the source is legally scrapable or manually provided.
                                </li>
                            </ul>
                        </div>
                        <div className="bg-slate-900 rounded-2xl p-6 text-white overflow-hidden relative">
                            <div className="relative z-10">
                                <h3 className="text-lg font-semibold mb-2">Automated Discovery v15</h3>
                                <p className="text-slate-400 text-sm mb-4">
                                    The RegEngine global discovery engine has scanned 1,200+ sources tonight.
                                    Low-confidence links and disallowed domains are routed here for human intelligence injection.
                                </p>
                                <div className="flex items-center gap-2 text-indigo-400 text-sm font-medium">
                                    Learn about the Ethics Engine
                                    <ArrowRight className="h-4 w-4" />
                                </div>
                            </div>
                            <div className="absolute top-0 right-0 p-8 opacity-10">
                                <Globe className="h-24 w-24" />
                            </div>
                        </div>
                    </div>
                </div>
            </PageContainer>
        </div>
    );
}

function ArrowRight(props: SVGProps<SVGSVGElement>) {
    return (
        <svg
            {...props}
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <path d="M5 12h14" />
            <path d="M12 5l7 7-7 7" />
        </svg>
    );
}
