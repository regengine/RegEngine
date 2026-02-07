'use client';

import { cn } from '@/lib/utils';
import { AlertTriangle, CheckCircle2, AlertCircle, XCircle } from 'lucide-react';

interface RiskCategory {
    id: string;
    name: string;
    score: number;
    tasks: number;
    status: 'low' | 'medium' | 'high' | 'critical';
}

interface RiskHeatMapProps {
    categories: RiskCategory[];
    selectedCategory: string | null;
    onSelectCategory: (id: string | null) => void;
}

const statusConfig = {
    low: {
        bg: 'bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/30',
        border: 'border-emerald-200 dark:border-emerald-800',
        text: 'text-emerald-700 dark:text-emerald-400',
        icon: CheckCircle2,
        label: 'Low Risk',
    },
    medium: {
        bg: 'bg-amber-50 hover:bg-amber-100 dark:bg-amber-950/30',
        border: 'border-amber-200 dark:border-amber-800',
        text: 'text-amber-700 dark:text-amber-400',
        icon: AlertCircle,
        label: 'Medium',
    },
    high: {
        bg: 'bg-orange-50 hover:bg-orange-100 dark:bg-orange-950/30',
        border: 'border-orange-200 dark:border-orange-800',
        text: 'text-orange-700 dark:text-orange-400',
        icon: AlertTriangle,
        label: 'High',
    },
    critical: {
        bg: 'bg-red-50 hover:bg-red-100 dark:bg-red-950/30',
        border: 'border-red-200 dark:border-red-800',
        text: 'text-red-700 dark:text-red-400',
        icon: XCircle,
        label: 'Critical',
    },
};

export function RiskHeatMap({ categories, selectedCategory, onSelectCategory }: RiskHeatMapProps) {
    return (
        <div className="grid grid-cols-2 gap-3">
            {categories.map((category) => {
                const config = statusConfig[category.status];
                const Icon = config.icon;
                const isSelected = selectedCategory === category.id;

                return (
                    <button
                        key={category.id}
                        onClick={() => onSelectCategory(isSelected ? null : category.id)}
                        className={cn(
                            'p-4 rounded-xl border-2 transition-all duration-200 text-left',
                            config.bg,
                            isSelected ? 'ring-2 ring-offset-2 ring-blue-500' : config.border
                        )}
                    >
                        <div className="flex items-start justify-between mb-2">
                            <Icon className={cn('h-5 w-5', config.text)} />
                            <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', config.bg, config.text)}>
                                {config.label}
                            </span>
                        </div>
                        <h4 className="font-medium text-sm mb-1 text-slate-900 dark:text-slate-100">
                            {category.name}
                        </h4>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span>{category.score}/100</span>
                            <span>•</span>
                            <span>{category.tasks} {category.tasks === 1 ? 'task' : 'tasks'}</span>
                        </div>
                    </button>
                );
            })}
        </div>
    );
}
