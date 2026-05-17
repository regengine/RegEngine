import { Skeleton } from '@/components/ui/skeleton';

export function AuthenticatedScreenLoading() {
    return (
        <div className="min-h-[60vh] p-6">
            <div className="mx-auto w-full max-w-6xl space-y-6" aria-busy="true" aria-label="Loading workspace">
                <div className="space-y-3">
                    <Skeleton className="h-4 w-48" />
                    <Skeleton className="h-9 w-64" />
                    <Skeleton className="h-4 w-full max-w-xl" />
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                    {[0, 1, 2].map((item) => (
                        <div key={item} className="rounded-lg border border-[var(--re-surface-border)] bg-card p-4">
                            <Skeleton className="h-5 w-28" />
                            <Skeleton className="mt-4 h-8 w-20" />
                            <Skeleton className="mt-3 h-3 w-full" />
                            <Skeleton className="mt-2 h-3 w-3/4" />
                        </div>
                    ))}
                </div>

                <div className="rounded-lg border border-[var(--re-surface-border)] bg-card p-4">
                    <div className="flex items-center justify-between gap-4">
                        <Skeleton className="h-6 w-40" />
                        <Skeleton className="h-9 w-28" />
                    </div>
                    <div className="mt-4 space-y-3">
                        {[0, 1, 2, 3, 4].map((item) => (
                            <Skeleton key={item} className="h-12 w-full" />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
