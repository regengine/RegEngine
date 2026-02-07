'use client';

import { cn } from '@/lib/utils';
import {
    FileText,
    FileCheck,
    FileWarning,
    Upload,
    Clock,
    CheckCircle2,
    XCircle,
    ExternalLink,
    Eye,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';

export type DocumentStatus = 'pending' | 'uploading' | 'uploaded' | 'verified' | 'rejected';

export interface TrackedDocument {
    id: string;
    name: string;
    type: string;
    category: 'permits' | 'insurance' | 'labor' | 'minors' | 'safety' | 'union';
    status: DocumentStatus;
    uploadProgress?: number;
    uploadedAt?: string;
    verifiedAt?: string;
    rejectionReason?: string;
    fileUrl?: string;
}

interface DocumentTrackerProps {
    documents: TrackedDocument[];
    onUpload?: (category: string) => void;
    onView?: (document: TrackedDocument) => void;
}

const statusConfig: Record<DocumentStatus, {
    icon: typeof FileText;
    label: string;
    color: string;
    bgColor: string;
}> = {
    pending: {
        icon: Clock,
        label: 'Pending',
        color: 'text-slate-500',
        bgColor: 'bg-slate-100 dark:bg-slate-800',
    },
    uploading: {
        icon: Upload,
        label: 'Uploading',
        color: 'text-blue-500',
        bgColor: 'bg-blue-50 dark:bg-blue-950/30',
    },
    uploaded: {
        icon: FileCheck,
        label: 'Uploaded',
        color: 'text-amber-500',
        bgColor: 'bg-amber-50 dark:bg-amber-950/30',
    },
    verified: {
        icon: CheckCircle2,
        label: 'Verified',
        color: 'text-emerald-500',
        bgColor: 'bg-emerald-50 dark:bg-emerald-950/30',
    },
    rejected: {
        icon: XCircle,
        label: 'Rejected',
        color: 'text-red-500',
        bgColor: 'bg-red-50 dark:bg-red-950/30',
    },
};

const categoryColors: Record<string, string> = {
    permits: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
    insurance: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    labor: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    minors: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    safety: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
    union: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
};

function DocumentCard({ document, onView }: { document: TrackedDocument; onView?: (doc: TrackedDocument) => void }) {
    const config = statusConfig[document.status];
    const Icon = config.icon;

    return (
        <div className={cn(
            'p-4 rounded-xl border transition-all duration-200',
            config.bgColor,
            'border-slate-200 dark:border-slate-700'
        )}>
            <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                    <Icon className={cn('h-5 w-5', config.color)} />
                    <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', categoryColors[document.category])}>
                        {document.category.charAt(0).toUpperCase() + document.category.slice(1)}
                    </span>
                </div>
                <span className={cn('text-xs font-medium', config.color)}>
                    {config.label}
                </span>
            </div>

            <h4 className="font-medium text-sm mb-1 text-slate-900 dark:text-slate-100">
                {document.name}
            </h4>
            <p className="text-xs text-muted-foreground mb-2">
                {document.type}
            </p>

            {document.status === 'uploading' && document.uploadProgress !== undefined && (
                <div className="mb-2">
                    <Progress value={document.uploadProgress} className="h-1.5" />
                    <p className="text-xs text-muted-foreground mt-1">{document.uploadProgress}% complete</p>
                </div>
            )}

            {document.status === 'rejected' && document.rejectionReason && (
                <p className="text-xs text-red-600 dark:text-red-400 mb-2">
                    ⚠️ {document.rejectionReason}
                </p>
            )}

            {document.uploadedAt && (
                <p className="text-xs text-muted-foreground">
                    Uploaded: {new Date(document.uploadedAt).toLocaleDateString()}
                </p>
            )}

            {document.status === 'uploaded' || document.status === 'verified' ? (
                <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2 w-full justify-center"
                    onClick={() => onView?.(document)}
                >
                    <Eye className="h-3 w-3 mr-1" />
                    View Document
                </Button>
            ) : document.status === 'pending' ? (
                <Button
                    variant="outline"
                    size="sm"
                    className="mt-2 w-full justify-center"
                    onClick={() => onView?.(document)}
                >
                    <Upload className="h-3 w-3 mr-1" />
                    Upload Now
                </Button>
            ) : null}
        </div>
    );
}

export function DocumentTracker({ documents, onUpload, onView }: DocumentTrackerProps) {
    const stats = {
        total: documents.length,
        verified: documents.filter(d => d.status === 'verified').length,
        pending: documents.filter(d => d.status === 'pending').length,
        rejected: documents.filter(d => d.status === 'rejected').length,
    };

    const completionPercent = stats.total > 0
        ? Math.round((stats.verified / stats.total) * 100)
        : 0;

    return (
        <div className="space-y-4">
            {/* Summary Bar */}
            <div className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
                <div className="flex items-center gap-4 text-sm">
                    <span className="font-medium">{stats.verified}/{stats.total} Complete</span>
                    {stats.pending > 0 && (
                        <span className="text-amber-600 dark:text-amber-400">
                            {stats.pending} pending
                        </span>
                    )}
                    {stats.rejected > 0 && (
                        <span className="text-red-600 dark:text-red-400">
                            {stats.rejected} rejected
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <Progress value={completionPercent} className="w-24 h-2" />
                    <span className="text-sm font-medium">{completionPercent}%</span>
                </div>
            </div>

            {/* Document Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {documents.map((doc) => (
                    <DocumentCard key={doc.id} document={doc} onView={onView} />
                ))}
            </div>

            {documents.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                    <FileText className="h-12 w-12 mx-auto mb-2 opacity-50" />
                    <p>No documents tracked yet</p>
                    <Button variant="outline" size="sm" className="mt-2" onClick={() => onUpload?.('general')}>
                        <Upload className="h-4 w-4 mr-2" />
                        Upload First Document
                    </Button>
                </div>
            )}
        </div>
    );
}
