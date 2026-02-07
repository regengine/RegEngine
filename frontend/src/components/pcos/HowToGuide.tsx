'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
    ChevronDown,
    ChevronUp,
    ExternalLink,
    Clock,
    FileText,
    CheckCircle2,
    Circle,
    AlertTriangle,
    Upload
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

interface GuideStep {
    id: number;
    text: string;
    completed: boolean;
    link?: string;
}

interface Guide {
    id: string;
    title: string;
    category: string;
    priority: 'critical' | 'high' | 'medium' | 'low';
    deadline: string;
    daysUntil: number;
    steps: GuideStep[];
    documentsRequired: string[];
    estimatedTime: string;
}

interface HowToGuideProps {
    guide: Guide;
    onUpload?: () => void;
}

const priorityConfig = {
    critical: {
        badge: 'bg-red-100 text-red-700 border-red-200',
        icon: 'text-red-500',
        border: 'border-l-red-500',
    },
    high: {
        badge: 'bg-orange-100 text-orange-700 border-orange-200',
        icon: 'text-orange-500',
        border: 'border-l-orange-500',
    },
    medium: {
        badge: 'bg-amber-100 text-amber-700 border-amber-200',
        icon: 'text-amber-500',
        border: 'border-l-amber-500',
    },
    low: {
        badge: 'bg-emerald-100 text-emerald-700 border-emerald-200',
        icon: 'text-emerald-500',
        border: 'border-l-emerald-500',
    },
};

export function HowToGuide({ guide, onUpload }: HowToGuideProps) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [completedSteps, setCompletedSteps] = useState<number[]>(
        guide.steps.filter(s => s.completed).map(s => s.id)
    );
    const config = priorityConfig[guide.priority];
    const completedCount = completedSteps.length;
    const totalSteps = guide.steps.length;
    const progressPercent = Math.round((completedCount / totalSteps) * 100);

    const toggleStep = (stepId: number) => {
        setCompletedSteps(prev =>
            prev.includes(stepId)
                ? prev.filter(id => id !== stepId)
                : [...prev, stepId]
        );
    };

    return (
        <div className={cn(
            'border rounded-xl overflow-hidden transition-all duration-200',
            'bg-white dark:bg-slate-900',
            'border-l-4',
            config.border
        )}>
            {/* Header - Always Visible */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full p-4 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
                <div className="flex items-center gap-3">
                    <AlertTriangle className={cn('h-5 w-5', config.icon)} />
                    <div className="text-left">
                        <h4 className="font-medium text-sm">{guide.title}</h4>
                        <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs text-muted-foreground">
                                {completedCount}/{totalSteps} steps
                            </span>
                            <span className="text-xs text-muted-foreground">•</span>
                            <span className={cn('text-xs', guide.daysUntil <= 3 ? 'text-red-500 font-medium' : 'text-muted-foreground')}>
                                Due in {guide.daysUntil} days
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <Badge variant="outline" className={config.badge}>
                        {guide.priority.toUpperCase()}
                    </Badge>
                    {isExpanded ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                    ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    )}
                </div>
            </button>

            {/* Expanded Content */}
            {isExpanded && (
                <div className="px-4 pb-4 border-t bg-slate-50/50 dark:bg-slate-800/50">
                    {/* Progress Bar */}
                    <div className="py-3">
                        <div className="h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                            <div
                                className="h-full bg-gradient-to-r from-blue-500 to-emerald-500 transition-all duration-300"
                                style={{ width: `${progressPercent}%` }}
                            />
                        </div>
                    </div>

                    {/* Steps Checklist */}
                    <div className="space-y-2 mb-4">
                        {guide.steps.map((step) => {
                            const isCompleted = completedSteps.includes(step.id);
                            return (
                                <div
                                    key={step.id}
                                    className={cn(
                                        'flex items-start gap-3 p-3 rounded-lg transition-colors cursor-pointer',
                                        isCompleted
                                            ? 'bg-emerald-50 dark:bg-emerald-900/20'
                                            : 'bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800'
                                    )}
                                    onClick={() => toggleStep(step.id)}
                                >
                                    {isCompleted ? (
                                        <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                                    ) : (
                                        <Circle className="h-5 w-5 text-slate-300 flex-shrink-0 mt-0.5" />
                                    )}
                                    <div className="flex-1">
                                        <span className={cn(
                                            'text-sm',
                                            isCompleted && 'line-through text-muted-foreground'
                                        )}>
                                            {step.text}
                                        </span>
                                        {step.link && (
                                            <a
                                                href={step.link}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="flex items-center gap-1 text-xs text-blue-500 hover:text-blue-600 mt-1"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <ExternalLink className="h-3 w-3" />
                                                External resource
                                            </a>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {/* Documents Required */}
                    <div className="mb-4">
                        <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
                            Documents Required
                        </h5>
                        <div className="flex flex-wrap gap-2">
                            {guide.documentsRequired.map((doc) => (
                                <Badge key={doc} variant="outline" className="text-xs">
                                    <FileText className="h-3 w-3 mr-1" />
                                    {doc}
                                </Badge>
                            ))}
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="flex items-center justify-between pt-3 border-t">
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Clock className="h-3 w-3" />
                            <span>Est. time: {guide.estimatedTime}</span>
                        </div>
                        {onUpload && (
                            <Button size="sm" variant="outline" onClick={onUpload}>
                                <Upload className="h-4 w-4 mr-2" />
                                Upload Evidence
                            </Button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
