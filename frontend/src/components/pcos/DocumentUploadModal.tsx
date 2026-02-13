'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
    Upload,
    FileText,
    X,
    CheckCircle2,
    AlertCircle,
    File,
    FileImage,
    FileSpreadsheet,
    Building2,
    Shield,
    Baby,
    ShieldCheck,
    Briefcase,
    Users,
    ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export type DocumentCategory = 'permits' | 'insurance' | 'labor' | 'minors' | 'safety' | 'union';

interface UploadedFile {
    id: string;
    file: File;
    progress: number;
    status: 'pending' | 'uploading' | 'success' | 'error';
    error?: string;
}

interface DocumentUploadModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    projectId?: string;
    preselectedCategory?: DocumentCategory;
    onUploadComplete?: (files: File[], category: DocumentCategory) => void;
}

type CategoryOption = {
    value: DocumentCategory;
    label: string;
    description: string;
    icon: React.ComponentType<{ className?: string }>;
    color: string;
};

const categoryOptions: CategoryOption[] = [
    {
        value: 'permits',
        label: 'Permits & Licenses',
        description: 'FilmLA permits, location agreements',
        icon: Building2,
        color: 'blue'
    },
    {
        value: 'insurance',
        label: 'Insurance',
        description: 'COI, workers comp, E&O policies',
        icon: Shield,
        color: 'emerald'
    },
    {
        value: 'labor',
        label: 'Labor & Contracts',
        description: 'Deal memos, crew agreements',
        icon: Users,
        color: 'purple'
    },
    {
        value: 'minors',
        label: 'Minor Protection',
        description: 'Work permits, studio teacher certs',
        icon: Baby,
        color: 'red'
    },
    {
        value: 'safety',
        label: 'Safety & IIPP',
        description: 'Safety plans, hazard assessments',
        icon: ShieldCheck,
        color: 'amber'
    },
    {
        value: 'union',
        label: 'Union Compliance',
        description: 'SAG signatory docs, pension forms',
        icon: Briefcase,
        color: 'indigo'
    },
];

function getFileIcon(file: File) {
    const type = file.type;
    if (type.startsWith('image/')) return FileImage;
    if (type.includes('spreadsheet') || type.includes('excel') || file.name.endsWith('.csv')) return FileSpreadsheet;
    return FileText;
}

function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentUploadModal({ open, onOpenChange, projectId, preselectedCategory, onUploadComplete }: DocumentUploadModalProps) {
    const [selectedCategory, setSelectedCategory] = useState<DocumentCategory | null>(preselectedCategory || null);
    const [files, setFiles] = useState<UploadedFile[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const [isUploading, setIsUploading] = useState(false);
    const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(preselectedCategory ? 2 : 1);
    const [statusMessage, setStatusMessage] = useState<string>('');
    const fileInputRef = useRef<HTMLInputElement>(null);
    const previousFocusRef = useRef<HTMLElement | null>(null);

    const handleFiles = useCallback((newFiles: FileList | File[]) => {
        const fileArray = Array.from(newFiles);
        const uploadedFiles: UploadedFile[] = fileArray.map((file) => ({
            id: `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
            file,
            progress: 0,
            status: 'pending',
        }));
        setFiles((prev) => [...prev, ...uploadedFiles]);
    }, []);

    const handleDragOver = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
    }, []);

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        if (e.dataTransfer.files.length > 0) {
            handleFiles(e.dataTransfer.files);
        }
    }, [handleFiles]);

    const removeFile = useCallback((id: string) => {
        setFiles((prev) => prev.filter((f) => f.id !== id));
    }, []);

    const uploadFiles = useCallback(async () => {
        if (!selectedCategory || files.length === 0) return;

        setIsUploading(true);

        const successfulFiles: File[] = [];

        // Upload each file
        for (let i = 0; i < files.length; i++) {
            const uploadedFile = files[i];
            const fileId = uploadedFile.id;

            // Set to uploading
            setFiles((prev) =>
                prev.map((f) => (f.id === fileId ? { ...f, status: 'uploading', progress: 0 } : f))
            );

            try {
                // Create form data for the upload
                const formData = new FormData();
                formData.append('file', uploadedFile.file);
                formData.append('category', selectedCategory);
                if (projectId) {
                    formData.append('project_id', projectId);
                }
                formData.append('entity_type', 'project');

                // Start progress animation
                const progressInterval = setInterval(() => {
                    setFiles((prev) =>
                        prev.map((f) => {
                            if (f.id === fileId && f.status === 'uploading' && f.progress < 90) {
                                return { ...f, progress: Math.min(f.progress + 10, 90) };
                            }
                            return f;
                        })
                    );
                }, 200);

                // Upload to API
                const response = await fetch('/api/pcos/documents/upload', {
                    method: 'POST',
                    body: formData,
                });

                clearInterval(progressInterval);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || 'Upload failed');
                }

                // Set to success
                setFiles((prev) =>
                    prev.map((f) => (f.id === fileId ? { ...f, status: 'success', progress: 100 } : f))
                );
                successfulFiles.push(uploadedFile.file);

            } catch (error) {
                const errorMessage = error instanceof Error ? error.message : 'Upload failed';
                setFiles((prev) =>
                    prev.map((f) => (f.id === fileId ? { ...f, status: 'error', error: errorMessage } : f))
                );
            }
        }

        setIsUploading(false);

        // Notify parent of completion if any files succeeded
        if (onUploadComplete && successfulFiles.length > 0) {
            onUploadComplete(successfulFiles, selectedCategory);
        }

        // Reset after a brief delay if all files succeeded
        const allSucceeded = files.length === successfulFiles.length;
        if (allSucceeded) {
            setTimeout(() => {
                setFiles([]);
                setSelectedCategory(null);
                onOpenChange(false);
            }, 1000);
        }
    }, [files, selectedCategory, projectId, onUploadComplete, onOpenChange]);

    const handleClose = useCallback(() => {
        if (!isUploading) {
            setFiles([]);
            setSelectedCategory(null);
            setStatusMessage('');
            onOpenChange(false);
            // Restore focus to the element that opened the modal
            if (previousFocusRef.current) {
                previousFocusRef.current.focus();
            }
        }
    }, [isUploading, onOpenChange]);

    const allUploaded = files.length > 0 && files.every((f) => f.status === 'success');

    // Store the currently focused element when modal opens
    useEffect(() => {
        if (open) {
            previousFocusRef.current = document.activeElement as HTMLElement;
        }
    }, [open]);

    // Announce upload status changes to screen readers
    useEffect(() => {
        if (files.length === 0) return;

        const uploading = files.filter(f => f.status === 'uploading').length;
        const complete = files.filter(f => f.status === 'success').length;
        const errors = files.filter(f => f.status === 'error').length;

        if (uploading > 0) {
            setStatusMessage(`Uploading ${uploading} ${uploading === 1 ? 'file' : 'files'}`);
        } else if (complete === files.length) {
            setStatusMessage(`All ${complete} ${complete === 1 ? 'file' : 'files'} uploaded successfully`);
        } else if (errors > 0) {
            setStatusMessage(`${errors} ${errors === 1 ? 'file' : 'files'} failed to upload`);
        }
    }, [files]);

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-2xl backdrop-blur-md" aria-describedby="upload-instructions">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Upload className="h-5 w-5 text-purple-600" aria-hidden="true" />
                        Upload Documents
                    </DialogTitle>
                    <DialogDescription id="upload-instructions">
                        Upload compliance documents for your production. Supported formats: PDF, DOC, DOCX, JPG, PNG.
                    </DialogDescription>
                </DialogHeader>

                {/* Screen reader status announcements */}
                <div role="status" aria-live="polite" aria-atomic="true" className="sr-only">
                    {statusMessage}
                </div>

                {/* Step Indicator */}
                <div className="flex items-center justify-center gap-1 py-4 border-y bg-slate-50/50 dark:bg-slate-800/50">
                    {[
                        { num: 1, label: 'Category' },
                        { num: 2, label: 'Files' },
                        { num: 3, label: 'Review' }
                    ].map((step, idx) => (
                        <div key={step.num} className="flex items-center">
                            <div className="flex flex-col items-center gap-1">
                                <div className={cn(
                                    "h-8 w-8 rounded-full flex items-center justify-center text-sm font-semibold transition-all",
                                    step.num < currentStep && "bg-purple-600 text-white",
                                    step.num === currentStep && "bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300 border-2 border-purple-600",
                                    step.num > currentStep && "bg-slate-100 dark:bg-slate-700 text-slate-400"
                                )}>
                                    {step.num < currentStep ? <CheckCircle2 className="h-4 w-4" /> : step.num}
                                </div>
                                <span className={cn(
                                    "text-xs font-medium",
                                    step.num <= currentStep ? "text-purple-700 dark:text-purple-300" : "text-slate-400"
                                )}>
                                    {step.label}
                                </span>
                            </div>
                            {idx < 2 && (
                                <ChevronRight className={cn(
                                    "h-4 w-4 mx-2",
                                    step.num < currentStep ? "text-purple-600" : "text-slate-300"
                                )} />
                            )}
                        </div>
                    ))}
                </div>

                <div className="space-y-4">
                    {/* Category Selection */}
                    <div className="space-y-2">
                        <label className="text-sm font-medium">Document Category</label>
                        <div className="grid grid-cols-2 gap-3">
                            {categoryOptions.map((cat) => {
                                const Icon = cat.icon;
                                return (
                                    <button
                                        key={cat.value}
                                        onClick={() => {
                                            setSelectedCategory(cat.value);
                                            if (currentStep === 1) setCurrentStep(2);
                                        }}
                                        disabled={isUploading}
                                        className={cn(
                                            'relative p-4 rounded-xl border-2 text-center transition-all',
                                            'hover:scale-[1.02] hover:shadow-md',
                                            selectedCategory === cat.value
                                                ? 'border-purple-500 bg-gradient-to-br from-purple-50 to-indigo-50 dark:from-purple-950/30 dark:to-indigo-950/30 shadow-lg'
                                                : 'border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600',
                                            isUploading && 'opacity-50 cursor-not-allowed'
                                        )}
                                    >
                                        <Icon className={cn(
                                            "h-8 w-8 mx-auto mb-2",
                                            selectedCategory === cat.value ? "text-purple-600 dark:text-purple-400" : "text-slate-500"
                                        )} />
                                        <div className="font-semibold text-sm">{cat.label}</div>
                                        <div className="text-xs text-muted-foreground mt-1">{cat.description}</div>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Drop Zone */}
                    <div
                        role="button"
                        tabIndex={isUploading ? -1 : 0}
                        aria-label="Upload files by clicking or dragging and dropping. Accepts PDF, DOC, DOCX, JPG, PNG files up to 10MB each."
                        aria-disabled={isUploading}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => !isUploading && fileInputRef.current?.click()}
                        onKeyDown={(e) => {
                            if ((e.key === 'Enter' || e.key === ' ') && !isUploading) {
                                e.preventDefault();
                                fileInputRef.current?.click();
                            }
                        }}
                        className={cn(
                            'relative border-3 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all',
                            'bg-gradient-to-br from-slate-50 to-white dark:from-slate-800/50 dark:to-slate-900/50',
                            isDragging
                                ? 'border-purple-500 bg-purple-50/50 dark:bg-purple-950/30 scale-[1.02] shadow-xl'
                                : 'border-slate-300 dark:border-slate-600 hover:border-slate-400 dark:hover:border-slate-500 hover:shadow-md',
                            isUploading && 'opacity-50 cursor-not-allowed'
                        )}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                            onChange={(e) => {
                                if (e.target.files) {
                                    handleFiles(e.target.files);
                                    if (currentStep === 2) setCurrentStep(3);
                                }
                            }}
                            className="hidden"
                            disabled={isUploading}
                        />
                        <Upload className={cn(
                            "h-16 w-16 mx-auto mb-4 transition-all",
                            isDragging ? "text-purple-600 scale-110" : "text-purple-500"
                        )} />
                        <p className="text-lg font-semibold mb-2">
                            {isDragging ? 'Drop files here!' : 'Drag & drop files'}
                        </p>
                        <p className="text-sm text-muted-foreground">
                            or{' '}
                            <button
                                type="button"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    fileInputRef.current?.click();
                                }}
                                className="text-purple-600 hover:text-purple-700 underline font-medium"
                            >
                                browse from computer
                            </button>
                        </p>
                        <p className="text-xs text-muted-foreground mt-3">
                            PDF, DOC, DOCX, JPG, PNG up to 10MB each
                        </p>
                    </div>

                    {/* File List */}
                    {files.length > 0 && (
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                            {files.map((uploadedFile) => {
                                const FileIcon = getFileIcon(uploadedFile.file);
                                return (
                                    <div
                                        key={uploadedFile.id}
                                        className="flex items-center gap-3 p-2 rounded-lg bg-slate-50 dark:bg-slate-800/50"
                                    >
                                        <FileIcon className="h-5 w-5 text-slate-500 flex-shrink-0" />
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium truncate">
                                                {uploadedFile.file.name}
                                            </p>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs text-muted-foreground">
                                                    {formatFileSize(uploadedFile.file.size)}
                                                </span>
                                                {uploadedFile.status === 'uploading' && (
                                                    <Progress value={uploadedFile.progress} className="h-1 flex-1" />
                                                )}
                                            </div>
                                        </div>
                                        {uploadedFile.status === 'pending' && !isUploading && (
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    removeFile(uploadedFile.id);
                                                }}
                                                className="p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded"
                                            >
                                                <X className="h-4 w-4 text-muted-foreground" />
                                            </button>
                                        )}
                                        {uploadedFile.status === 'success' && (
                                            <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0" />
                                        )}
                                        {uploadedFile.status === 'error' && (
                                            <div className="flex items-center gap-1">
                                                <span className="text-xs text-red-500 max-w-[100px] truncate" title={uploadedFile.error}>
                                                    {uploadedFile.error}
                                                </span>
                                                <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={handleClose} disabled={isUploading}>
                        Cancel
                    </Button>
                    <Button
                        onClick={uploadFiles}
                        disabled={!selectedCategory || files.length === 0 || isUploading || allUploaded}
                    >
                        {isUploading ? (
                            <>Uploading...</>
                        ) : allUploaded ? (
                            <>
                                <CheckCircle2 className="h-4 w-4 mr-2" />
                                Done
                            </>
                        ) : (
                            <>
                                <Upload className="h-4 w-4 mr-2" />
                                Upload {files.length > 0 ? `(${files.length})` : ''}
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
