'use client';

import React from 'react';
import { captureError } from '@/instrumentation-client';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';

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

    componentDidCatch() {
        captureError(new Error('Dashboard render failed'));
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="flex min-h-[60vh] items-center justify-center px-4 py-10">
                    <Callout
                        tone="danger"
                        role="alert"
                        title="Something went wrong"
                        className="w-full max-w-md"
                        action={
                            <Button
                                type="button"
                                variant="secondary"
                                leadingIcon={<RefreshCw className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
                                onClick={() => {
                                    this.setState({ hasError: false, error: null });
                                    window.location.reload();
                                }}
                            >
                                Reload Page
                            </Button>
                        }
                    >
                        An unexpected error occurred while rendering this page.
                    </Callout>
                </div>
            );
        }

        return this.props.children;
    }
}
