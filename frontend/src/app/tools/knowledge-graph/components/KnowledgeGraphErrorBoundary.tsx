'use client';

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface Props {
    children: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class KnowledgeGraphErrorBoundary extends Component<Props, State> {
    public state: State = {
        hasError: false,
        error: null,
    };

    public static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error("Knowledge Graph Rendering Error:", error, errorInfo);
    }

    private handleReset = () => {
        this.setState({ hasError: false, error: null });
    };

    public render() {
        if (this.state.hasError) {
            return (
                <Card className="rounded-3xl border-destructive/50 bg-destructive/10">
                    <CardContent className="flex flex-col items-center justify-center p-12 text-center space-y-4">
                        <div className="rounded-full bg-destructive/20 p-4">
                            <AlertTriangle className="h-10 w-10 text-destructive" />
                        </div>
                        <div className="space-y-2">
                            <h3 className="text-xl font-bold">Physics Engine Halted</h3>
                            <p className="text-sm text-muted-foreground max-w-sm mx-auto">
                                The Supply Chain Knowledge Graph encountered a rendering error. This usually happens when the WebGL/Canvas context is overwhelmed or invalid data is passed.
                            </p>
                        </div>
                        <Button 
                            variant="outline" 
                            className="mt-4 border-destructive/30 hover:bg-destructive/20"
                            onClick={this.handleReset}
                        >
                            <RotateCcw className="mr-2 h-4 w-4" />
                            Reinitialize Graph
                        </Button>
                    </CardContent>
                </Card>
            );
        }

        return this.props.children;
    }
}
