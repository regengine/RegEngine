'use client';

import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ServiceUnavailableProps {
    service: string;
    message?: string;
    onRetry?: () => void;
}

export function ServiceUnavailable({ service, message, onRetry }: ServiceUnavailableProps) {
    return (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-6 text-center">
            <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-3" />
            <p className="text-sm font-medium text-foreground">
                Unable to reach {service} service
            </p>
            <p className="text-xs text-muted-foreground mt-1">
                {message || 'This feature requires backend connectivity. Please try again shortly.'}
            </p>
            {onRetry ? (
                <button
                    onClick={onRetry}
                    className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-amber-500/20 text-amber-600 hover:bg-amber-500/10 transition-colors"
                >
                    <RefreshCw className="h-3 w-3" />
                    Retry
                </button>
            ) : (
                <button
                    onClick={() => window.location.reload()}
                    className="mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-amber-500/20 text-amber-600 hover:bg-amber-500/10 transition-colors"
                >
                    <RefreshCw className="h-3 w-3" />
                    Reload Page
                </button>
            )}
        </div>
    );
}