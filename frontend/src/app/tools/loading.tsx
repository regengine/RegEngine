export default function ToolsLoading() {
    return (
        <div className="p-6 space-y-6 animate-pulse">
            {/* Header skeleton */}
            <div className="space-y-2">
                <div className="h-8 w-40 bg-muted rounded" />
                <div className="h-4 w-72 bg-muted rounded" />
            </div>

            {/* Tool cards skeleton */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div key={i} className="h-40 bg-muted rounded-xl" />
                ))}
            </div>
        </div>
    );
}
