import Link from 'next/link';

export default function VerticalsPage() {
    return (
        <div className="min-h-screen bg-re-surface-card dark:bg-re-surface-base">
            <div className="bg-gradient-to-r from-gray-900 to-gray-800 dark:from-black dark:to-gray-900">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-24 text-center">
                    <h1 className="font-display text-5xl md:text-6xl font-bold text-white mb-6">
                        FSMA-First Product Surface
                    </h1>
                    <p className="text-xl text-re-text-secondary mb-8 max-w-3xl mx-auto">
                        RegEngine is currently focused on food safety and FSMA 204 traceability workflows.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link
                            href="/verticals/food-safety"
                            className="px-8 py-4 bg-white text-re-text-primary rounded-lg font-semibold hover:bg-re-surface-elevated transition-colors"
                        >
                            Open Food Safety
                        </Link>
                        <Link
                            href="/tools/fsma-unified"
                            className="px-8 py-4 bg-re-surface-elevated text-white rounded-lg font-semibold hover:bg-gray-600 transition-colors"
                        >
                            Open FSMA Dashboard
                        </Link>
                    </div>
                </div>
            </div>

            <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
                <div className="rounded-2xl border border-re-border dark:border-re-border bg-white dark:bg-re-surface-card p-8">
                    <h2 className="text-2xl font-bold text-re-text-primary dark:text-re-text-primary mb-3">Current Focus</h2>
                    <p className="text-re-text-disabled dark:text-re-text-secondary mb-4">
                        RegEngine is currently focused on FSMA 204 traceability workflows for food supply chains.
                    </p>
                    <p className="text-sm text-re-text-muted dark:text-re-text-tertiary">
                        Product documentation, tooling, and onboarding on this site are aligned to food safety and traceability operations.
                    </p>
                </div>
            </div>
        </div>
    );
}
