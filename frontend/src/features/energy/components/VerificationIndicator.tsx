/**
 * Verification Indicator Component
 * 
 * PASSIVE instrument panel - makes corruption observable.
 * 
 * Rules:
 * - Displays verification state verbatim (no derivation)
 * - Neutral styling (instrument panel, not alarm)
 * - No actions (read-only)
 * - Polls in background (60s via hook)
 */

import { useVerifyLatestSnapshot } from '../api/queries/useVerification';

interface VerificationIndicatorProps {
    substationId: string;
    snapshotId?: string; // Optional: verify specific snapshot
}

export const VerificationIndicator = ({ substationId }: VerificationIndicatorProps) => {
    const { data, isLoading } = useVerifyLatestSnapshot(substationId);

    if (isLoading || !data) {
        return (
            <div className="inline-flex items-center gap-1.5 rounded-md bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
                <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Verifying...</span>
            </div>
        );
    }

    // Map status to visual state (reflect, don't derive)
    const stateConfig = {
        valid: {
            className: 'bg-green-50 text-green-700 border border-green-200',
            icon: '✓',
            label: 'Verified'
        },
        corrupted: {
            className: 'bg-red-50 text-red-700 border border-red-200',
            icon: '✕',
            label: 'Corrupted'
        },
        no_snapshots: {
            className: 'bg-gray-50 text-gray-600 border border-gray-200',
            icon: '○',
            label: 'No Baseline'
        }
    };

    const state = stateConfig[data.status] || stateConfig.no_snapshots;

    return (
        <div className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium ${state.className}`}>
            <span className="font-semibold">{state.icon}</span>
            <span>{state.label}</span>
        </div>
    );
};
