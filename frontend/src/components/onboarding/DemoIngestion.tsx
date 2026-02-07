'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { useIngestURL } from '@/hooks/use-api';
import { Loader2, Play, Rocket, ChevronRight } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';
import { toast } from '@/components/ui/use-toast';
import { useDemoProgress } from './DemoProgress';

export function DemoIngestion() {
    const [isLoading, setIsLoading] = useState(false);
    const [isTourLoading, setIsTourLoading] = useState(false);
    const { apiKey, setApiKey, setTenantId, completeOnboarding } = useAuth();
    const ingestMutation = useIngestURL();
    const router = useRouter();
    const { startDemo, isActive: isDemoActive } = useDemoProgress();

    // Setup demo credentials and return the API key
    const setupDemoCredentials = async (): Promise<string | null> => {
        let currentApiKey = apiKey;

        if (!currentApiKey) {
            toast({
                title: "Setting up Demo Environment",
                description: "Creating a temporary tenant for your session...",
            });

            const setupRes = await fetch('/api/setup-demo', { method: 'POST' });
            if (!setupRes.ok) throw new Error("Failed to setup demo environment");

            const data = await setupRes.json();
            currentApiKey = data.apiKey;

            // Save to global context
            setApiKey(data.apiKey);
            setTenantId(data.tenantId);
            completeOnboarding();

            // Small delay to ensure state updates
            await new Promise(resolve => setTimeout(resolve, 500));
        }

        return currentApiKey;
    };

    const handleIngest = async () => {
        setIsLoading(true);

        try {
            const currentApiKey = await setupDemoCredentials();

            if (!currentApiKey) {
                toast({
                    title: "Authentication Required",
                    description: "Could not auto-provision demo credentials. Please run setup.",
                    variant: "destructive"
                });
                return;
            }

            // DORA Regulation URL
            const DORA_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R2554";

            await ingestMutation.mutateAsync({
                apiKey: currentApiKey,
                url: DORA_URL,
                sourceSystem: "eur-lex"
            });

            toast({
                title: "Ingestion Started",
                description: "DORA Regulation is being processed by the engine.",
            });

            // Redirect to ingestion dashboard
            router.push('/ingest');

        } catch (error) {
            console.error("Demo ingestion failed", error);
            toast({
                title: "Ingestion Failed",
                description: error instanceof Error ? error.message : "Could not start demo ingestion.",
                variant: "destructive"
            });
        } finally {
            setIsLoading(false);
        }
    };

    const handleStartFullTour = async () => {
        setIsTourLoading(true);

        try {
            const currentApiKey = await setupDemoCredentials();

            if (!currentApiKey) {
                toast({
                    title: "Authentication Required",
                    description: "Could not auto-provision demo credentials.",
                    variant: "destructive"
                });
                return;
            }

            // Start the demo progress tracker
            startDemo();

            // DORA Regulation URL
            const DORA_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=CELEX:32022R2554";

            toast({
                title: "🚀 Full Demo Starting",
                description: "Ingesting DORA regulation and preparing your guided tour...",
            });

            await ingestMutation.mutateAsync({
                apiKey: currentApiKey,
                url: DORA_URL,
                sourceSystem: "eur-lex"
            });

            toast({
                title: "✅ Ingestion Complete",
                description: "Document queued for processing. Let's explore!",
            });

            // Navigate to ingestion page as the first step
            router.push('/ingest');

        } catch (error) {
            console.error("Full tour failed to start", error);
            toast({
                title: "Tour Failed",
                description: error instanceof Error ? error.message : "Could not start the full demo tour.",
                variant: "destructive"
            });
        } finally {
            setIsTourLoading(false);
        }
    };

    return (
        <div className="mt-4 p-4 border rounded-lg bg-slate-50 dark:bg-slate-900">
            <h4 className="font-semibold text-sm mb-2">See It In Action</h4>
            <p className="text-xs text-muted-foreground mb-3">
                Experience RegEngine with the <strong>EU Digital Operational Resilience Act (DORA)</strong> from EUR-Lex.
            </p>

            <div className="space-y-2">
                {/* Primary: Full Demo Tour */}
                <Button
                    size="sm"
                    onClick={handleStartFullTour}
                    disabled={isLoading || isTourLoading || isDemoActive}
                    className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white"
                >
                    {isTourLoading ? (
                        <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Starting Tour...
                        </>
                    ) : isDemoActive ? (
                        <>
                            <Rocket className="mr-2 h-4 w-4" />
                            Tour In Progress
                        </>
                    ) : (
                        <>
                            <Rocket className="mr-2 h-4 w-4" />
                            Start Full Demo Tour
                            <ChevronRight className="ml-1 h-4 w-4" />
                        </>
                    )}
                </Button>

                {/* Secondary: Quick Ingest Only */}
                <Button
                    size="sm"
                    variant="outline"
                    onClick={handleIngest}
                    disabled={isLoading || isTourLoading}
                    className="w-full"
                >
                    {isLoading ? (
                        <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            Ingesting DORA...
                        </>
                    ) : (
                        <>
                            <Play className="mr-2 h-4 w-4" />
                            Quick Ingest Only
                        </>
                    )}
                </Button>
            </div>
        </div>
    );
}
