export default function SettingsLoading() {
    return (
        <div className="p-6 space-y-6 animate-pulse">
            {/* Header skeleton */}
            <div className="space-y-2">
                <div className="h-8 w-48 bg-muted rounded" />
                <div className="h-4 w-72 bg-muted rounded" />
            </div>

            {/* Settings sections skeleton */}
            <div className="space-y-6">
                {[1, 2, 3].map((i) => (
                    <div key={i} className="space-y-4 border-b border-muted pb-6">
                        <div className="h-6 w-40 bg-muted rounded" />
                        <div className="space-y-3">
                            <div className="h-4 w-24 bg-muted rounded" />
                            <div className="h-10 w-full bg-muted rounded-lg" />
                            <div className="h-4 w-32 bg-muted rounded" />
                            <div className="h-10 w-full bg-muted rounded-lg" />
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
