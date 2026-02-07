import { Link2, AlertTriangle, Sparkles } from 'lucide-react';

interface ChainStatusProps {
    status: 'valid' | 'broken' | 'genesis';
    previousSnapshotId: string | null;
}

export function ChainStatus({ status, previousSnapshotId }: ChainStatusProps) {
    return (
        <div className="space-y-4">
            {/* Status Indicator */}
            <div className="flex items-center gap-3">
                {status === 'valid' && (
                    <>
                        <Link2 className="h-6 w-6 text-green-600" />
                        <span className="text-lg font-medium text-green-600">Chain Intact</span>
                    </>
                )}
                {status === 'broken' && (
                    <>
                        <AlertTriangle className="h-6 w-6 text-red-600" />
                        <span className="text-lg font-medium text-red-600">Chain Broken</span>
                    </>
                )}
                {status === 'genesis' && (
                    <>
                        <Sparkles className="h-6 w-6 text-blue-600" />
                        <span className="text-lg font-medium text-blue-600">Genesis Snapshot</span>
                    </>
                )}
            </div>

            {/* Previous Snapshot Link */}
            {previousSnapshotId && (
                <div>
                    <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">
                        Previous Snapshot
                    </dt>
                    <dd className="mt-1">
                        <a
                            href={`/snapshots/${previousSnapshotId}`}
                            className="font-mono text-xs text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 break-all underline"
                        >
                            {previousSnapshotId}
                        </a>
                    </dd>
                </div>
            )}

            {!previousSnapshotId && (
                <p className="text-sm text-gray-500 dark:text-gray-400">
                    This is the first snapshot in the chain for this substation
                </p>
            )}
        </div>
    );
}
