import Link from 'next/link';

export default function VerticalsPage() {
    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <div className="bg-gradient-to-r from-gray-900 to-gray-800 dark:from-black dark:to-gray-900">
                <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-24 text-center">
                    <h1 className="font-display text-5xl md:text-6xl font-bold text-white mb-6">
                        FSMA-First Product Surface
                    </h1>
                    <p className="text-xl text-gray-300 mb-8 max-w-3xl mx-auto">
                        RegEngine is currently focused on food safety and FSMA 204 traceability workflows.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link
                            href="/verticals/food-safety"
                            className="px-8 py-4 bg-white text-gray-900 rounded-lg font-semibold hover:bg-gray-100 transition-colors"
                        >
                            Open Food Safety
                        </Link>
                        <Link
                            href="/tools/fsma-unified"
                            className="px-8 py-4 bg-gray-700 text-white rounded-lg font-semibold hover:bg-gray-600 transition-colors"
                        >
                            Open FSMA Dashboard
                        </Link>
                    </div>
                </div>
            </div>

            <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-14">
                <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-8">
                    <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-3">Current Focus</h2>
                    <p className="text-gray-600 dark:text-gray-300 mb-4">
                        RegEngine is currently focused on FSMA 204 traceability workflows for food supply chains.
                    </p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Product documentation, tooling, and onboarding on this site are aligned to food safety and traceability operations.
                    </p>
                </div>
            </div>
        </div>
    );
}
