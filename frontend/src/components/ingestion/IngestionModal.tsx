'use client';

import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Upload, Link2, AlertCircle, CheckCircle } from 'lucide-react';
import { useIngestURL, useIngestFile } from '@/hooks/use-api';
import { useAuth } from '@/lib/auth-context';
import { Spinner } from '@/components/ui/spinner';
import { AnalysisResults } from './AnalysisResults';
import { AnalysisSummary } from '@/types/api';
import { apiClient } from '@/lib/api-client';

interface IngestionModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    vertical?: string;
}

export function IngestionModal({ open, onOpenChange, vertical }: IngestionModalProps) {
    const { apiKey } = useAuth();
    const [activeTab, setActiveTab] = useState('url');
    const [url, setUrl] = useState('');
    const [file, setFile] = useState<File | null>(null);
    const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle');
    const [message, setMessage] = useState('');
    const [viewState, setViewState] = useState<'input' | 'analyzing' | 'results'>('input');
    const [analysisData, setAnalysisData] = useState<AnalysisSummary | null>(null);

    const ingestUrlMutation = useIngestURL();
    const ingestFileMutation = useIngestFile();

    const isPending = ingestUrlMutation.isPending || ingestFileMutation.isPending;
    const sourceSystem = vertical ? `vertical-${vertical}` : 'generic-upload';

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
            setStatus('idle');
        }
    };

    const handleSubmit = async () => {
        if (!apiKey) {
            setMessage('API Key required (please login or set key)');
            setStatus('error');
            return;
        }

        setStatus('idle');
        setMessage('');

        try {
            let result; // eslint-disable-line @typescript-eslint/no-unused-vars
            if (activeTab === 'url') {
                if (!url) return;
                result = await ingestUrlMutation.mutateAsync({ apiKey, url, sourceSystem });
            } else {
                if (!file) return;
                result = await ingestFileMutation.mutateAsync({ apiKey, file, sourceSystem });
            }

            setStatus('success');
            setMessage('Document successfully queued for processing.');

            // Poll for analysis
            if (result?.document_id) {
                setViewState('analyzing');
                try {
                    // Simulate short processing delay
                    await new Promise(r => setTimeout(r, 1500));
                    const analysis = await apiClient.getDocumentAnalysis(result.document_id, apiKey);
                    setAnalysisData(analysis);
                    setViewState('results');
                    return; // Don't auto-close
                } catch (e) {
                    console.error("Analysis fetch failed", e);
                    // Fallback to auto-close if analysis fails
                }
            }

            // Reset after delay (only if not showing results)
            setTimeout(() => {
                onOpenChange(false);
                setStatus('idle');
                setUrl('');
                setFile(null);
                setViewState('input');
            }, 2000);

        } catch (error: unknown) {
            console.error(error);
            setStatus('error');
            const message = error instanceof Error ? error.message : 'Ingestion failed';
            setMessage(message);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>Ingest Document</DialogTitle>
                    <DialogDescription>
                        Add a regulatory document to the {vertical ? vertical : 'RegEngine'} knowledge base.
                    </DialogDescription>
                </DialogHeader>

                {viewState === 'results' && analysisData ? (
                    <AnalysisResults
                        data={analysisData}
                        onClose={() => {
                            onOpenChange(false);
                            setViewState('input');
                            setStatus('idle');
                            setUrl('');
                            setFile(null);
                        }}
                    />
                ) : (
                    <>
                        {viewState === 'analyzing' && (
                            <div className="py-12 text-center space-y-4">
                                <Spinner size="lg" className="mx-auto" />
                                <div className="text-lg font-medium">Analyzing Document...</div>
                                <p className="text-muted-foreground text-sm">Extracting obligations and assessing risk.</p>
                            </div>
                        )}

                        {viewState === 'input' && (
                            <>
                                <Tabs value={activeTab} onValueChange={(v) => { setActiveTab(v); setStatus('idle'); }} className="w-full">
                                    <TabsList className="grid w-full grid-cols-2">
                                        <TabsTrigger value="url">URL</TabsTrigger>
                                        <TabsTrigger value="file">File Upload</TabsTrigger>
                                    </TabsList>

                                    <TabsContent value="url" className="space-y-4 py-4">
                                        <div className="space-y-2">
                                            <Label>Document URL</Label>
                                            <div className="relative">
                                                <Link2 className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                                                <Input
                                                    placeholder="https://example.com/doc.pdf"
                                                    className="pl-9"
                                                    value={url}
                                                    onChange={(e) => setUrl(e.target.value)}
                                                    disabled={isPending}
                                                />
                                            </div>
                                        </div>
                                    </TabsContent>

                                    <TabsContent value="file" className="space-y-4 py-4">
                                        <div className="border-2 border-dashed rounded-lg p-6 text-center hover:bg-muted/50 transition-colors">
                                            <Input
                                                type="file"
                                                onChange={handleFileChange}
                                                disabled={isPending}
                                                className="hidden"
                                                id="modal-file-upload"
                                                accept=".pdf,.html,.json,.xml,.docx,.txt"
                                            />
                                            <label htmlFor="modal-file-upload" className="cursor-pointer block">
                                                <Upload className="mx-auto h-10 w-10 text-muted-foreground mb-3" />
                                                <div className="text-sm font-medium">
                                                    {file ? file.name : 'Click to select file'}
                                                </div>
                                                {!file && <div className="text-xs text-muted-foreground mt-2">Max size: 20MB</div>}
                                            </label>
                                        </div>
                                    </TabsContent>
                                </Tabs>

                                {status === 'error' && (
                                    <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 p-3 rounded-md">
                                        <AlertCircle className="h-4 w-4" />
                                        {message}
                                    </div>
                                )}

                                {status === 'success' && (
                                    <div className="flex items-center gap-2 text-sm text-green-600 bg-green-50 p-3 rounded-md">
                                        <CheckCircle className="h-4 w-4" />
                                        {message}
                                    </div>
                                )}

                                <Button
                                    onClick={handleSubmit}
                                    disabled={isPending || (activeTab === 'url' ? !url : !file)}
                                    className="w-full mt-4"
                                >
                                    {isPending ? (
                                        <>
                                            <Spinner size="sm" className="mr-2" /> Processing...
                                        </>
                                    ) : 'Ingest Document'}
                                </Button>
                            </>
                        )}
                    </>
                )}

            </DialogContent>
        </Dialog >
    );
}
