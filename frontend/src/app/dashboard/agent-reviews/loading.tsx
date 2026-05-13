export default function AgentReviewsLoading() {
    return (
        <div className="p-6 space-y-5 animate-pulse">
            <div className="flex items-start justify-between gap-4">
                <div className="space-y-2">
                    <div className="h-7 w-56 rounded bg-[var(--re-surface-muted)]" />
                    <div className="h-4 w-96 max-w-full rounded bg-[var(--re-surface-muted)]" />
                </div>
                <div className="h-9 w-28 rounded bg-[var(--re-surface-muted)]" />
            </div>
            <div className="h-28 rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-base)]" />
            <div className="h-96 rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-base)]" />
        </div>
    );
}
