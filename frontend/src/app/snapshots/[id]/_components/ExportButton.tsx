'use client';

import { Download } from 'lucide-react';
import { useState } from 'react';

interface ExportButtonProps {
    snapshotId: string;
    substationId: string;
    isCorrupted: boolean;
}

/**
 * Export Button
 * 
 * Downloads snapshot as JSON with cryptographic verification data.
 * 
 * Invariant: Exported data includes:
 * - Raw snapshot content
 * - Cryptographic hashes (content_hash, signature_hash)
 * - Chain lineage (previous_snapshot_id)
 * - Verification metadata
 * 
 * CRITICAL: Export works even for corrupted snapshots (evidence preservation).
 */
export function ExportButton({ snapshotId, substationId, isCorrupted }: ExportButtonProps) {
    const [isExporting, setIsExporting] = useState(false);

    const handleExport = async () => {
        setIsExporting(true);

        try {
            const response = await fetch(`/api/snapshots/${snapshotId}/export`);

            if (!response.ok) {
                throw new Error('Export failed');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `snapshot-${substationId}-${snapshotId}.json`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            console.error('Export failed:', error);
            alert('Failed to export snapshot');
        } finally {
            setIsExporting(false);
        }
    };

    return (
        <button
            onClick={handleExport}
            disabled={isExporting}
            className={`
        inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium
        transition-colors
        ${isCorrupted
                    ? 'bg-yellow-100 hover:bg-yellow-200 text-yellow-900 border border-yellow-300 dark:bg-yellow-900/20 dark:hover:bg-yellow-900/30 dark:text-yellow-100 dark:border-yellow-700'
                    : 'bg-blue-600 hover:bg-blue-700 text-white'
                }
        disabled:opacity-50 disabled:cursor-not-allowed
      `}
            title={isCorrupted ? 'Export corrupted snapshot (evidence preservation)' : 'Export snapshot'}
        >
            <Download className="h-4 w-4" />
            {isExporting ? 'Exporting...' : 'Export JSON'}
            {isCorrupted && ' (Evidence)'}
        </button>
    );
}
