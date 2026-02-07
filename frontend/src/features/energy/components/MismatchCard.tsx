/**
 * Mismatch Card Component
 * 
 * READ-ONLY view with resolve affordance.
 * 
 * Rules:
 * - Displays mismatch verbatim (no derivation)
 * - "Resolve" button visible only when verification == 'valid'
 * - Enforcement remains in hook (component only reflects)
 * - Links to detection snapshot
 */

import { useState } from 'react';
import { useMismatchDetail } from '../api/queries/useMismatches';
import { useVerifyLatestSnapshot } from '../api/queries/useVerification';
import { AttestationModal } from './AttestationModal';
import type { Mismatch } from '../types/energy.types';

interface MismatchCardProps {
    mismatch: Mismatch;
    substationId: string;
}

export const MismatchCard = ({ mismatch, substationId }: MismatchCardProps) => {
    const [showAttestationModal, setShowAttestationModal] = useState(false);

    // Verification state (for button visibility - reflects, doesn't enforce)
    const { data: verificationData } = useVerifyLatestSnapshot(substationId);
    const canResolve = verificationData?.status === 'valid' && mismatch.status === 'OPEN';

    // Severity color mapping (reflects backend)
    const severityColors = {
        CRITICAL: 'bg-red-100 text-red-800 border-red-300',
        HIGH: 'bg-orange-100 text-orange-800 border-orange-300',
        MEDIUM: 'bg-yellow-100 text-yellow-800 border-yellow-300',
        LOW: 'bg-gray-100 text-gray-700 border-gray-300'
    };

    const severityColor = severityColors[mismatch.severity];

    // Status color mapping
    const statusColors = {
        OPEN: 'bg-blue-100 text-blue-800 border-blue-300',
        RESOLVED: 'bg-green-100 text-green-800 border-green-300',
        RISK_ACCEPTED: 'bg-amber-100 text-amber-800 border-amber-300'
    };

    const statusColor = statusColors[mismatch.status];

    return (
        <>
            <div className="rounded-lg border border-gray-200 bg-white shadow-sm hover:shadow-md transition-shadow">
                {/* Header */}
                <div className="p-4">
                    <div className="flex items-start justify-between">
                        {/* Severity badge */}
                        <span className={`inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold ${severityColor}`}>
                            {mismatch.severity}
                        </span>

                        {/* Status badge */}
                        <span className={`inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-medium ${statusColor}`}>
                            {mismatch.status.replace(/_/g, ' ')}
                        </span>
                    </div>

                    {/* Description */}
                    <div className="mt-3 text-sm font-medium text-gray-900">
                        {mismatch.description}
                    </div>

                    {/* Metadata */}
                    <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
                        <div>
                            Detected: {new Date(mismatch.created_at).toLocaleString('en-US', {
                                dateStyle: 'medium',
                                timeStyle: 'short'
                            })}
                        </div>
                        {mismatch.detected_snapshot_id && (
                            <div className="font-mono">
                                Snapshot: {mismatch.detected_snapshot_id.slice(0, 8)}...
                            </div>
                        )}
                    </div>

                    {/* Resolution metadata (if resolved) */}
                    {mismatch.status !== 'OPEN' && mismatch.resolved_at && (
                        <div className="mt-3 rounded-md bg-gray-50 p-3 text-xs">
                            <div className="font-medium text-gray-900">Resolution</div>
                            <div className="mt-1 text-gray-600">
                                Resolved: {new Date(mismatch.resolved_at).toLocaleString()}
                            </div>

                            {mismatch.resolution_justification && (
                                <div className="mt-2">
                                    <div className="font-medium text-gray-700">Justification:</div>
                                    <div className="mt-1 text-gray-600">{mismatch.resolution_justification}</div>
                                </div>
                            )}

                            {mismatch.attester_name && (
                                <div className="mt-2 text-gray-600">
                                    Attested by: {mismatch.attester_name} ({mismatch.attester_role})
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Actions */}
                {mismatch.status === 'OPEN' && (
                    <div className="border-t border-gray-100 px-4 py-3 flex justify-end">
                        <button
                            onClick={() => setShowAttestationModal(true)}
                            disabled={!canResolve}
                            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-gray-400"
                            title={!canResolve ? 'System integrity must be verified before resolutions' : 'Resolve this mismatch'}
                        >
                            Resolve Mismatch
                        </button>
                    </div>
                )}
            </div>

            {/* Attestation Modal (mutation happens here, enforced by hook) */}
            {showAttestationModal && (
                <AttestationModal
                    mismatchId={mismatch.id}
                    substationId={substationId}
                    mismatchDescription={mismatch.description}
                    isOpen={showAttestationModal}
                    onClose={() => setShowAttestationModal(false)}
                />
            )}
        </>
    );
};
