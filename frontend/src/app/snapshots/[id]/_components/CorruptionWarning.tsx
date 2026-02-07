'use client';

import { AlertTriangle } from 'lucide-react';

interface CorruptionWarningProps {
    corruptionType: string;
    detectedAt: string;
    affectedField?: string;
}

/**
 * Corruption Warning Banner
 * 
 * CRITICAL: This component renders ONLY when corruption is detected.
 * Must be visually dominant and unmissable.
 * 
 * Invariant: If visible, system is in SAFETY_MODE and mutations are blocked.
 */
export function CorruptionWarning({
    corruptionType,
    detectedAt,
    affectedField
}: CorruptionWarningProps) {
    return (
        <div className="border-2 border-red-600 bg-red-50 dark:bg-red-950/20 rounded-lg p-6 mb-6">
            <div className="flex items-start gap-4">
                <div className="flex-shrink-0">
                    <AlertTriangle className="h-8 w-8 text-red-600" />
                </div>

                <div className="flex-1">
                    <h3 className="text-lg font-semibold text-red-900 dark:text-red-100 mb-2">
                        Integrity Corruption Detected
                    </h3>

                    <div className="space-y-2 text-sm text-red-800 dark:text-red-200">
                        <p>
                            <span className="font-medium">Type:</span>{' '}
                            <code className="px-2 py-0.5 bg-red-100 dark:bg-red-900/40 rounded">
                                {corruptionType}
                            </code>
                        </p>

                        {affectedField && (
                            <p>
                                <span className="font-medium">Affected Field:</span>{' '}
                                <code className="px-2 py-0.5 bg-red-100 dark:bg-red-900/40 rounded">
                                    {affectedField}
                                </code>
                            </p>
                        )}

                        <p>
                            <span className="font-medium">Detected:</span>{' '}
                            {new Date(detectedAt).toLocaleString()}
                        </p>
                    </div>

                    <div className="mt-4 pt-4 border-t border-red-200 dark:border-red-800">
                        <p className="text-sm font-medium text-red-900 dark:text-red-100">
                            ⚠️ Safety Mode Active
                        </p>
                        <p className="text-sm text-red-700 dark:text-red-300 mt-1">
                            All compliance-affecting mutations are blocked until integrity is restored.
                            This snapshot cannot be used for regulatory reporting.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
