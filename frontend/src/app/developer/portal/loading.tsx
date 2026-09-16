import { Skeleton } from '@/components/ui/skeleton';

export default function PortalLoading() {
    return (
        <div className="space-y-6">
            <div className="space-y-2 border-b border-re-border-subtle pb-5">
                <Skeleton className="h-8 w-64" />
                <Skeleton className="h-4 w-full max-w-[38ch]" />
            </div>
            <Skeleton className="h-48 w-full rounded-lg" />
            <div className="space-y-3">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-5/6" />
                <Skeleton className="h-4 w-2/3" />
            </div>
        </div>
    );
}
