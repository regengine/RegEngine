export default function PortalLoading() {
    return (
        <div className="max-w-[900px] mx-auto px-6 py-16 space-y-6 animate-pulse">
            <div className="h-10 w-64 bg-muted rounded" />
            <div className="h-4 w-full bg-muted rounded" />
            <div className="h-4 w-3/4 bg-muted rounded" />
            <div className="h-48 w-full bg-muted rounded-xl mt-8" />
            <div className="space-y-3 mt-8">
                <div className="h-4 w-full bg-muted rounded" />
                <div className="h-4 w-5/6 bg-muted rounded" />
                <div className="h-4 w-2/3 bg-muted rounded" />
            </div>
        </div>
    );
}
