'use client';

import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
}

export class DashboardErrorBoundary extends React.Component<
    { children: React.ReactNode },
    ErrorBoundaryState
> {
    constructor(props: { children: React.ReactNode }) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error: Error): ErrorBoundaryState {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: React.ErrorInfo) {
        if (process.env.NODE_ENV !== 'production') {
            console.error('[DashboardErrorBoundary]', error, info.componentStack);
        }
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="flex flex-col items-center justify-center min-h-[60vh] p-8 text-center">
                    <div className="w-14 h-14 rounded-2xl bg-re-danger-muted0/10 flex items-center justify-center mb-4">
                        <AlertTriangle className="h-7 w-7 text-re-danger" />
                    </div>
                    <h2 className="text-lg font-semibold mb-2">Something went wrong</h2>
                    <p className="text-sm text-muted-foreground max-w-md mb-6">
                        An unexpected error occurred while rendering this page.
                        {this.state.error?.message && (
                            <span className="block mt-2 font-mono text-xs text-re-danger/80">
                                {this.state.error.message}
                            </span>
                        )}
                    </p>
                    <button
                        onClick={() => {
                            this.setState({ hasError: false, error: null });
                            window.location.reload();
                        }}
                        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[var(--re-brand)] text-white text-sm font-medium hover:brightness-110 active:scale-[0.97] transition-all"
                    >
                        <RefreshCw className="h-4 w-4" />
                        Reload Page
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}
