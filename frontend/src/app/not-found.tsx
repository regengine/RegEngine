import Link from 'next/link';
import { FileQuestion, Home, Wrench } from 'lucide-react';

export default function NotFound() {
    return (
        <div className="flex items-center justify-center min-h-[70vh] p-6">
            <div className="max-w-md w-full text-center space-y-6">
                <div className="mx-auto w-16 h-16 rounded-2xl bg-re-info-muted0/10 flex items-center justify-center">
                    <FileQuestion className="h-8 w-8 text-re-info" />
                </div>

                <div>
                    <h1 className="text-2xl font-semibold mb-2">Page Not Found</h1>
                    <p className="text-sm text-muted-foreground">
                        This page doesn&apos;t exist. It may have been moved, renamed, or removed.
                    </p>
                </div>

                <div className="flex flex-col sm:flex-row gap-3 justify-center">
                    <Link
                        href="/"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[var(--re-brand)] text-white text-sm font-medium hover:opacity-90 transition-opacity"
                    >
                        <Home className="h-4 w-4" />
                        Back to Home
                    </Link>
                    <Link
                        href="/tools"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-re-border dark:border-re-border text-sm font-medium hover:bg-re-surface-card dark:hover:bg-re-surface-card transition-colors"
                    >
                        <Wrench className="h-4 w-4" />
                        Free Tools
                    </Link>
                </div>
            </div>
        </div>
    );
}
