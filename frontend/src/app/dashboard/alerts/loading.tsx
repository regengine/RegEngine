export default function AlertsLoading() {
    return (
        <div className="p-6 space-y-6 animate-pulse">
            {/* Breadcrumb skeleton */}
            <div className="h-4 w-48 bg-muted rounded" />

            {/* Header skeleton */}
            <div className="space-y-2">
                <div className="h-8 w-40 bg-muted rounded" />
                <div className="h-4 w-72 bg-muted rounded" />
            </div>

            {/* Alert cards skeleton */}
            <div className="space-y-3">
                {[1, 2, 3, 4, 5].map((i) => (
                    <div key={i} className="h-20 bg-muted rounded-xl" />
                ))}
            </div>
        </div>
    );
}
