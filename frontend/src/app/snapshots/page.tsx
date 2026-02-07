import { Suspense } from 'react';
import Link from 'next/link';

interface Snapshot {
    id: string;
    substation_id: string;
    facility_name: string;
    snapshot_time: string;
    system_status: string;
    verification_status: string;
    chain_status: string;
}

async function getSnapshots(): Promise<Snapshot[]> {
    // Mock data for now - will be replaced with API call
    return [
        {
            id: '00000000-0000-0000-0000-000000000002',
            substation_id: 'TEST-ALPHA',
            facility_name: 'Alpha Test Station',
            snapshot_time: '2026-01-25T19:00:00Z',
            system_status: 'DEGRADED',
            verification_status: 'valid',
            chain_status: 'valid',
        },
        {
            id: '00000000-0000-0000-0000-000000000001',
            substation_id: 'TEST-ALPHA',
            facility_name: 'Alpha Test Station',
            snapshot_time: '2026-01-25T18:00:00Z',
            system_status: 'NOMINAL',
            verification_status: 'valid',
            chain_status: 'genesis',
        },
    ];
}

function StatusBadge({ status }: { status: string }) {
    const colors = {
        NOMINAL: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
        DEGRADED: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
        NON_COMPLIANT: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    };

    return (
        <span className={`px-2 py-1 rounded text-xs font-medium ${colors[status as keyof typeof colors] || 'bg-gray-100'}`}>
            {status}
        </span>
    );
}

function ChainBadge({ status }: { status: string }) {
    const config = {
        genesis: { icon: '✨', color: 'text-blue-600', label: 'Genesis' },
        valid: { icon: '🔗', color: 'text-green-600', label: 'Linked' },
        broken: { icon: '⚠️', color: 'text-red-600', label: 'Broken' },
    };

    const { icon, color, label } = config[status as keyof typeof config] || config.valid;

    return (
        <span className={`text-sm ${color}`}>
            {icon} {label}
        </span>
    );
}

export default async function SnapshotsPage() {
    const snapshots = await getSnapshots();

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
                        Compliance Snapshots
                    </h1>
                    <p className="mt-2 text-gray-600 dark:text-gray-400">
                        Immutable compliance snapshots for energy substations
                    </p>
                </div>

                {/*Stats */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <div className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Total Snapshots
                        </div>
                        <div className="mt-2 text-3xl font-bold text-gray-900 dark:text-gray-100">
                            {snapshots.length}
                        </div>
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <div className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            NOMINAL Status
                        </div>
                        <div className="mt-2 text-3xl font-bold text-green-600">
                            {snapshots.filter(s => s.system_status === 'NOMINAL').length}
                        </div>
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                        <div className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Needs Attention
                        </div>
                        <div className="mt-2 text-3xl font-bold text-yellow-600">
                            {snapshots.filter(s => s.system_status !== 'NOMINAL').length}
                        </div>
                    </div>
                </div>

                {/* Table */}
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-900">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Time
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Facility
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Status
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Chain
                                </th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                    Actions
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                            {snapshots.map((snapshot) => (
                                <tr
                                    key={snapshot.id}
                                    className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition-colors"
                                >
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100">
                                        {new Date(snapshot.snapshot_time).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                                            {snapshot.facility_name}
                                        </div>
                                        <div className="text-sm text-gray-500 dark:text-gray-400">
                                            {snapshot.substation_id}
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <StatusBadge status={snapshot.system_status} />
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <ChainBadge status={snapshot.chain_status} />
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                                        <Link
                                            href={`/snapshots/${snapshot.id}`}
                                            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 font-medium"
                                        >
                                            View Details →
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Empty state for no snapshots */}
                {snapshots.length === 0 && (
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-12 text-center">
                        <p className="text-gray-500 dark:text-gray-400">
                            No snapshots found. Create your first snapshot to get started.
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
