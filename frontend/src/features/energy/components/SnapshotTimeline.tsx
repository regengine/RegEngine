/**
 * Snapshot Timeline Component
 * 
 * READ-ONLY temporal lens over immutable snapshots.
 * 
 * Rules:
 * - Uses query hooks only (no mutations)
 * - Backend order only (no client sorting)
 * - No derived status
 * - No local state
 * - Pagination via backend cursors
 */

import { useState } from 'react';
import { useSnapshots } from '../api/queries/useSnapshots';
import { SnapshotCard } from './SnapshotCard';
import type { SystemStatus } from '../types/energy.types';

interface SnapshotTimelineProps {
    substationId: string;
}

export const SnapshotTimeline = ({ substationId }: SnapshotTimelineProps) => {
    const [offset, setOffset] = useState(0);
    const [statusFilter, setStatusFilter] = useState<SystemStatus | undefined>();
    const [fromTime, setFromTime] = useState<string | undefined>();
    const [toTime, setToTime] = useState<string | undefined>();

    const LIMIT = 50;

    // Query snapshots (read-only)
    const { data, isLoading, error, isError } = useSnapshots({
        substation_id: substationId,
        limit: LIMIT,
        offset,
        status: statusFilter,
        from_time: fromTime,
        to_time: toTime
    });

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="text-sm text-gray-500">Loading snapshots...</div>
            </div>
        );
    }

    if (isError) {
        return (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                <div className="text-sm font-medium text-red-800">
                    Failed to load snapshots
                </div>
                <div className="mt-1 text-sm text-red-600">
                    {error instanceof Error ? error.message : 'Unknown error'}
                </div>
            </div>
        );
    }

    if (!data || data.snapshots.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12">
                <div className="text-sm font-medium text-gray-900">No snapshots found</div>
                <div className="mt-1 text-sm text-gray-500">
                    {statusFilter || fromTime || toTime
                        ? 'Try adjusting your filters'
                        : 'No compliance snapshots exist yet'}
                </div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900">Compliance Timeline</h2>
                    <p className="mt-1 text-sm text-gray-500">
                        {data.total} snapshots total
                    </p>
                </div>

                {/* Filters */}
                <div className="flex gap-3">
                    <select
                        value={statusFilter || ''}
                        onChange={(e) => setStatusFilter(e.target.value as SystemStatus || undefined)}
                        className="rounded-md border border-gray-300 px-3 py-2 text-sm"
                    >
                        <option value="">All Status</option>
                        <option value="NOMINAL">Nominal</option>
                        <option value="DEGRADED">Degraded</option>
                        <option value="NON_COMPLIANT">Non-Compliant</option>
                    </select>
                </div>
            </div>

            {/* Timeline */}
            <div className="relative">
                {/* Timeline axis */}
                <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-gray-200" />

                {/* Snapshot cards */}
                <div className="space-y-6">
                    {data.snapshots.map((snapshot) => (
                        <SnapshotCard
                            key={snapshot.id}
                            snapshot={snapshot}
                            substationId={substationId}
                        />
                    ))}
                </div>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between border-t border-gray-200 pt-4">
                <div className="text-sm text-gray-600">
                    Showing {offset + 1} - {Math.min(offset + LIMIT, data.total)} of {data.total}
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                        disabled={offset === 0}
                        className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        Previous
                    </button>

                    <button
                        onClick={() => setOffset(offset + LIMIT)}
                        disabled={!data.has_more}
                        className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        Next
                    </button>
                </div>
            </div>
        </div>
    );
};
