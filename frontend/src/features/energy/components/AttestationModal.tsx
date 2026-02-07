/**
 * Attestation Modal Component
 * 
 * ONLY mutation surface in Phase 1C.
 * 
 * Rules:
 * - Uses SEALED useResolveMismatch hook (verification gate enforced)
 * - No optimistic UI
 * - On success: close modal, rely on cache invalidation
 * - On integrity failure: surface error verbatim, do not retry
 * - Validation client-side is UX only (backend validates)
 */

import { useState } from 'react';
import { useResolveMismatch } from '../api/mutations/useResolveMismatch';

interface AttestationModalProps {
    mismatchId: string;
    substationId: string;
    mismatchDescription: string;
    isOpen: boolean;
    onClose: () => void;
}

export const AttestationModal = ({
    mismatchId,
    substationId,
    mismatchDescription,
    isOpen,
    onClose
}: AttestationModalProps) => {
    const [resolutionType, setResolutionType] = useState<'RESOLVED' | 'RISK_ACCEPTED'>('RESOLVED');
    const [justification, setJustification] = useState('');
    const [attesterName, setAttesterName] = useState('');
    const [attesterRole, setAttesterRole] = useState('');
    const [signature, setSignature] = useState('');
    const [validationError, setValidationError] = useState('');

    // Mutation hook (SEALED - verification gate enforced inside)
    const resolveMutation = useResolveMismatch(substationId);

    const handleSubmit = () => {
        setValidationError('');

        // Client-side validation (UX only - backend also validates)
        if (justification.length < 20) {
            setValidationError('Justification must be at least 20 characters');
            return;
        }

        if (!attesterName || !attesterRole) {
            setValidationError('Attester name and role are required');
            return;
        }

        if (signature !== attesterName) {
            setValidationError('Signature must match attester name exactly');
            return;
        }

        // Submit mutation (verification gate checked inside hook)
        resolveMutation.mutate(
            {
                mismatchId,
                request: {
                    resolution_type: resolutionType,
                    justification,
                    attestation: {
                        attester_name: attesterName,
                        attester_role: attesterRole,
                        signature
                    }
                }
            },
            {
                onSuccess: () => {
                    // Close modal - cache invalidation handled by hook
                    onClose();
                }
            }
        );
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
            <div className="w-full max-w-lg rounded-lg bg-white shadow-xl">
                {/* Header */}
                <div className="border-b border-gray-200 px-6 py-4">
                    <h3 className="text-lg font-semibold text-gray-900">Resolve Mismatch</h3>
                    <p className="mt-1 text-sm text-gray-600">{mismatchDescription}</p>
                </div>

                {/* Body */}
                <div className="px-6 py-4 space-y-4">
                    {/* Resolution Type */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700">
                            Resolution Type
                        </label>
                        <div className="mt-2 space-y-2">
                            <label className="flex items-center">
                                <input
                                    type="radio"
                                    value="RESOLVED"
                                    checked={resolutionType === 'RESOLVED'}
                                    onChange={(e) => setResolutionType(e.target.value as 'RESOLVED')}
                                    className="h-4 w-4 text-blue-600"
                                />
                                <span className="ml-2 text-sm text-gray-700">
                                    Resolved (asset verified/fixed)
                                </span>
                            </label>
                            <label className="flex items-center">
                                <input
                                    type="radio"
                                    value="RISK_ACCEPTED"
                                    checked={resolutionType === 'RISK_ACCEPTED'}
                                    onChange={(e) => setResolutionType(e.target.value as 'RISK_ACCEPTED')}
                                    className="h-4 w-4 text-blue-600"
                                />
                                <span className="ml-2 text-sm text-gray-700">
                                    Risk Accepted (acknowledged but not fixed)
                                </span>
                            </label>
                        </div>
                    </div>

                    {/* Justification */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700">
                            Justification (min 20 characters)
                        </label>
                        <textarea
                            value={justification}
                            onChange={(e) => setJustification(e.target.value)}
                            rows={4}
                            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                            placeholder="Describe the resolution or accepted risk..."
                        />
                        <div className="mt-1 text-xs text-gray-500">
                            {justification.length} / 20 characters minimum
                        </div>
                    </div>

                    {/* Attestation */}
                    <div className="rounded-md bg-amber-50 border border-amber-200 p-4">
                        <div className="text-sm font-medium text-amber-900">Attestation Required</div>
                        <div className="mt-2 space-y-3">
                            <div>
                                <label className="block text-xs font-medium text-amber-800">
                                    Your Name
                                </label>
                                <input
                                    type="text"
                                    value={attesterName}
                                    onChange={(e) => setAttesterName(e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-amber-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                                    placeholder="John Smith"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-medium text-amber-800">
                                    Your Role
                                </label>
                                <input
                                    type="text"
                                    value={attesterRole}
                                    onChange={(e) => setAttesterRole(e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-amber-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                                    placeholder="Compliance Officer"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-medium text-amber-800">
                                    Digital Signature (type your name exactly)
                                </label>
                                <input
                                    type="text"
                                    value={signature}
                                    onChange={(e) => setSignature(e.target.value)}
                                    className="mt-1 block w-full rounded-md border border-amber-300 px-3 py-2 text-sm font-mono focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
                                    placeholder="John Smith"
                                />
                            </div>

                            <div className="text-xs text-amber-700">
                                ⚠️ By signing, you attest this resolution is accurate and compliant with NERC CIP-013
                            </div>
                        </div>
                    </div>

                    {/* Errors */}
                    {validationError && (
                        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                            {validationError}
                        </div>
                    )}

                    {/* Mutation error (includes INTEGRITY_VIOLATION from hook) */}
                    {resolveMutation.isError && (
                        <div className="rounded-md bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                            <div className="font-medium">Failed to resolve mismatch</div>
                            <div className="mt-1">
                                {resolveMutation.error instanceof Error
                                    ? resolveMutation.error.message
                                    : 'Unknown error'}
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="border-t border-gray-200 px-6 py-4 flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        disabled={resolveMutation.isPending}
                        className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={resolveMutation.isPending}
                        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {resolveMutation.isPending ? 'Submitting...' : 'Submit Attestation'}
                    </button>
                </div>
            </div>
        </div>
    );
};
