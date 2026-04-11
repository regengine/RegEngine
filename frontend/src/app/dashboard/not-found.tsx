import Link from 'next/link';
import { FileQuestion, Home } from 'lucide-react';

export default function DashboardNotFound() {
    return (
        <div className="flex items-center justify-center min-h-[60vh] p-6">
            <div className="max-w-md w-full text-center space-y-6">
                <div className="mx-auto w-16 h-16 rounded-2xl bg-re-info-muted0/10 flex items-center justify-center">
                    <FileQuestion className="h-8 w-8 text-re-info" />
                </div>

                <div>
                    <h2 className="text-xl font-semibold mb-2">Page Not Found</h2>
                    <p className="text-sm text-muted-foreground">
                        This dashboard page doesn&apos;t exist. It may have been moved or removed.
                    </p>
                </div>

                <Link
                    href="/dashboard"
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--re-brand)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
                >
                    <Home className="h-4 w-4" />
                    Back to Dashboard
                </Link>
            </div>
        </div>
    );
}
