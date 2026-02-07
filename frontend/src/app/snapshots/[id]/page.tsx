import { SnapshotStatusBadge } from './_components/SnapshotStatusBadge';
import { TimeDisplay } from './_components/TimeDisplay';
import { SnapshotMetadata } from './_components/SnapshotMetadata';
import { VerificationResult } from './_components/VerificationResult';
import { ChainStatus } from './_components/ChainStatus';
import { CorruptionWarning } from './_components/CorruptionWarning';
import { ExportButton } from './_components/ExportButton';

interface PageProps {
    params: Promise<{ id: string }>;
}

// Fetch snapshot from backend API
async function getSnapshot(id: string) {
    const response = await fetch(`http://localhost:3000/api/snapshots/${id}`, {
        cache: 'no-store', // Always fetch fresh data for compliance
    });

    if (!response.ok) {
        throw new Error('Failed to fetch snapshot');
    }

    return response.json();
}

export default async function SnapshotDetailPage({ params }: PageProps) {
    const { id } = await params;

    // Fetch snapshot from backend
    const snapshot = await getSnapshot(id);

    const isCorrupted = snapshot.verification_status === 'corrupted';
    const isChainBroken = snapshot.chain_status === 'broken';

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <div className="max-w-6xl mx-auto px-4 py-8">
                {/* Header */}
                <div className="mb-6">
                    <div className="flex items-start justify-between mb-4">
                        <div>
                            <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">
                                {snapshot.facility_name}
                            </h1>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                Snapshot ID: <code className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded">{snapshot.id}</code>
                            </p>
                        </div>

                        <div className="flex items-center gap-3">
                            <SnapshotStatusBadge status={snapshot.system_status} />
                            <ExportButton
                                snapshotId={snapshot.id}
                                substationId={snapshot.substation_id}
                                isCorrupted={isCorrupted}
                            />
                        </div>
                    </div>
                </div>

                {/* Corruption Warning - Only shows if corrupted */}
                {isCorrupted && snapshot.corruption_type && snapshot.corruption_detected_at && (
                    <CorruptionWarning
                        corruptionType={snapshot.corruption_type}
                        detectedAt={snapshot.corruption_detected_at}
                    />
                )}

                {/* Main Content Grid */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Left Column - Metadata */}
                    <div className="lg:col-span-1">
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                                Snapshot Metadata
                            </h2>
                            <SnapshotMetadata
                                snapshotTime={snapshot.snapshot_time}
                                createdAt={snapshot.created_at}
                                generatedBy={snapshot.generated_by}
                                substationId={snapshot.substation_id}
                            />
                        </div>
                    </div>

                    {/* Right Column - Verification & Chain */}
                    <div className="lg:col-span-2 space-y-6">
                        {/* Verification Status */}
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                                Cryptographic Verification
                            </h2>
                            <VerificationResult
                                status={snapshot.verification_status}
                                contentHash={snapshot.content_hash}
                                signatureHash={snapshot.signature_hash}
                            />
                        </div>

                        {/* Chain Status */}
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                                Chain Lineage
                            </h2>
                            <ChainStatus
                                status={snapshot.chain_status}
                                previousSnapshotId={snapshot.previous_snapshot_id}
                            />
                        </div>

                        {/* Compliance Data - Placeholder */}
                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
                            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                                Compliance State
                            </h2>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                Asset states, ESP configuration, and patch metrics will be displayed here.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
