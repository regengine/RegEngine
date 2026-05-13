export default function DashboardLoading() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] p-4 sm:p-6 space-y-6 sm:space-y-8 animate-pulse">
            <div className="h-4 w-48 rounded bg-muted" />

            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="space-y-2">
                    <div className="h-8 w-44 rounded bg-muted" />
                    <div className="h-4 w-[min(24rem,80vw)] rounded bg-muted" />
                </div>
                <div className="h-7 w-40 rounded bg-muted" />
            </div>

            <div className="h-[244px] rounded-lg bg-muted" />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-6">
                    <div className="h-[210px] rounded-lg bg-muted" />
                    <div className="h-[136px] rounded-lg bg-muted" />
                </div>
                <div className="space-y-6">
                    <div className="h-[220px] rounded-lg bg-muted" />
                    <div className="h-[260px] rounded-lg bg-muted" />
                </div>
            </div>

            <div className="space-y-4">
                <div className="h-6 w-36 rounded bg-muted" />
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
                    {[1, 2, 3].map((item) => (
                        <div key={item} className="h-[96px] rounded-lg bg-muted" />
                    ))}
                </div>
            </div>
        </div>
    );
}
