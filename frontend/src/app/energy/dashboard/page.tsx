import Link from 'next/link';
import { Activity, CheckCircle, AlertTriangle, TrendingUp } from 'lucide-react';

export default function EnergyDashboard() {
    // Mock data
    const data = {
        current_status: 'DEGRADED' as const,
        last_check_minutes: 2,
        total_assets: 12,
        verified_assets: 12,
        active_mismatches: 1,
        recent_snapshots: [
            { id: '00000000-0000-0000-0000-000000000002', time: '2026-01-25T19:00:00Z', status: 'DEGRADED' },
            { id: '00000000-0000-0000-0000-000000000001', time: '2026-01-25T18:00:00Z', status: 'NOMINAL' },
        ],
        chain_length: 2,
        chain_intact: true,
    };

    const statusColors = {
        NOMINAL: 'bg-green-500',
        DEGRADED: 'bg-yellow-500',
        NON_COMPLIANT: 'bg-red-500',
    };

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Header */}
                <div className="mb-8">
                    <div className="flex items-center justify-between">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                                Alpha Test Station
                            </h1>
                            <p className="mt-2 text-gray-600 dark:text-gray-400">
                                Live Compliance Dashboard
                            </p>
                        </div>
                        <Link
                            href="/snapshots"
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                        >
                            View All Snapshots
                        </Link>
                    </div>
                </div>

                {/* Status Banner */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8 mb-8">
                    <div className="flex items-center gap-4">
                        <div className={`${statusColors[data.current_status]} h-16 w-16 rounded-full flex items-center justify-center animate-pulse`}>
                            <Activity className="h-8 w-8 text-white" />
                        </div>
                        <div className="flex-1">
                            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                                Current Status: {data.current_status}
                            </div>
                            <div className="text-sm text-gray-600 dark:text-gray-400">
                                Last check: {data.last_check_minutes} minutes ago
                            </div>
                        </div>
                    </div>
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
                    {/* Assets */}
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <div className="flex items-center gap-3 mb-2">
                            <CheckCircle className="h-5 w-5 text-green-600" />
                            <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                                Assets
                            </span>
                        </div>
                        <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                            {data.verified_assets}/{data.total_assets}
                        </div>
                        <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            All Verified
                        </div>
                    </div>

                    {/* Mismatches */}
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <div className="flex items-center gap-3 mb-2">
                            <AlertTriangle className="h-5 w-5 text-yellow-600" />
                            <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                                Mismatches
                            </span>
                        </div>
                        <div className="text-3xl font-bold text-yellow-600">
                            {data.active_mismatches}
                        </div>
                        <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            Needs Review
                        </div>
                    </div>

                    {/* Chain Health */}
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <div className="flex items-center gap-3 mb-2">
                            <TrendingUp className="h-5 w-5 text-blue-600" />
                            <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                                Chain Status
                            </span>
                        </div>
                        <div className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                            {data.chain_intact ? '✅' : '❌'}
                        </div>
                        <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            {data.chain_length} snapshots
                        </div>
                    </div>

                    {/* Compliance Score */}
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <div className="flex items-center gap-3 mb-2">
                            <Activity className="h-5 w-5 text-purple-600" />
                            <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                                Compliance
                            </span>
                        </div>
                        <div className="text-3xl font-bold text-green-600">
                            98%
                        </div>
                        <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                            CIP-013 Compliant
                        </div>
                    </div>
                </div>

                {/* Recent Snapshots */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                        Latest Snapshots
                    </h2>
                    <div className="space-y-3">
                        {data.recent_snapshots.map((snapshot) => (
                            <Link
                                key={snapshot.id}
                                href={`/snapshots/${snapshot.id}`}
                                className="flex items-center justify-between p-4 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 transition-colors"
                            >
                                <div className="flex items-center gap-4">
                                    <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                        {new Date(snapshot.time).toLocaleTimeString()}
                                    </div>
                                    <span
                                        className={`px-2 py-1 rounded text-xs font-medium ${snapshot.status === 'NOMINAL'
                                                ? 'bg-green-100 text-green-800'
                                                : 'bg-yellow-100 text-yellow-800'
                                            }`}
                                    >
                                        {snapshot.status}
                                    </span>
                                </div>
                                <span className="text-blue-600 hover:text-blue-800 text-sm font-medium">
                                    View →
                                </span>
                            </Link>
                        ))}
                    </div>

                    <div className="mt-4 text-center">
                        <Link
                            href="/snapshots"
                            className="text-blue-600 hover:text-blue-800 text-sm font-medium"
                        >
                            View All Snapshots →
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
