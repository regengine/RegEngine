export default function ComplianceLoading() {
    return (
        <div className="p-6 space-y-6 animate-pulse">
            {/* Breadcrumb skeleton */}
            <div className="h-4 w-56 bg-muted rounded" />

            {/* Header skeleton */}
            <div className="space-y-2">
                <div className="h-8 w-72 bg-muted rounded" />
                <div className="h-4 w-96 bg-muted rounded" />
            </div>

            {/* Status cards skeleton */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="h-28 bg-muted rounded-xl" />
                ))}
            </div>

            {/* Table skeleton */}
            <div className="space-y-3">
                <div className="h-10 bg-muted rounded-lg" />
                {[1, 2, 3, 4, 5].map((i) => (
                    <div key={i} className="h-12 bg-muted rounded-lg" />
                ))}
            </div>
        </div>
    );
}
