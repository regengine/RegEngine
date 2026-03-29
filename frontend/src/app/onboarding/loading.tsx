export default function OnboardingLoading() {
    return (
        <div className="max-w-[600px] mx-auto px-6 py-16 space-y-6 animate-pulse">
            {/* Progress bar skeleton */}
            <div className="h-2 w-full bg-muted rounded-full" />

            {/* Header skeleton */}
            <div className="space-y-2">
                <div className="h-8 w-64 bg-muted rounded" />
                <div className="h-4 w-full bg-muted rounded" />
            </div>

            {/* Form skeleton */}
            <div className="space-y-4 mt-8">
                <div className="h-4 w-24 bg-muted rounded" />
                <div className="h-10 w-full bg-muted rounded-lg" />
                <div className="h-4 w-32 bg-muted rounded" />
                <div className="h-10 w-full bg-muted rounded-lg" />
                <div className="h-4 w-28 bg-muted rounded" />
                <div className="h-24 w-full bg-muted rounded-lg" />
            </div>

            {/* Button skeleton */}
            <div className="h-10 w-32 bg-muted rounded-lg mt-4" />
        </div>
    );
}
