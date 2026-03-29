export default function PricingLoading() {
    return (
        <div className="max-w-[900px] mx-auto px-6 py-16 space-y-6 animate-pulse">
            <div className="h-10 w-64 bg-muted rounded" />
            <div className="h-4 w-full bg-muted rounded" />
            <div className="h-4 w-3/4 bg-muted rounded" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
                {[1, 2, 3].map((i) => (
                    <div key={i} className="h-64 bg-muted rounded-xl" />
                ))}
            </div>
        </div>
    );
}
