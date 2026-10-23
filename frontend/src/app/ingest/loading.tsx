import { TimedSkeleton } from '@/components/ui/timed-skeleton';

export default function IngestLoading() {
    return (
        <TimedSkeleton className="p-6" errorMessage="The import page did not finish loading. Reload to try again.">
            <div className="space-y-6 animate-pulse">
                {/* Header skeleton */}
                <div className="space-y-2">
                    <div className="h-8 w-56 bg-muted rounded" />
                    <div className="h-4 w-80 bg-muted rounded" />
                </div>

                {/* Upload area skeleton */}
                <div className="h-48 w-full bg-muted rounded-xl border-2 border-dashed border-muted" />

                {/* Recent ingests table skeleton */}
                <div className="space-y-3">
                    <div className="h-10 bg-muted rounded-lg" />
                    {[1, 2, 3, 4].map((i) => (
                        <div key={i} className="h-12 bg-muted rounded-lg" />
                    ))}
                </div>
            </div>
        </TimedSkeleton>
    );
}
