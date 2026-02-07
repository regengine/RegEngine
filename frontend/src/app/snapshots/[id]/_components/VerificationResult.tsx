import { CheckCircle, XCircle, Clock } from 'lucide-react';

interface VerificationResultProps {
    status: 'valid' | 'corrupted' | 'pending';
    contentHash: string;
    signatureHash: string | null;
}

export function VerificationResult({
    status,
    contentHash,
    signatureHash,
}: VerificationResultProps) {
    return (
        <div className="space-y-4">
            {/* Status Indicator */}
            <div className="flex items-center gap-3">
                {status === 'valid' && (
                    <>
                        <CheckCircle className="h-6 w-6 text-green-600" />
                        <span className="text-lg font-medium text-green-600">Verified</span>
                    </>
                )}
                {status === 'corrupted' && (
                    <>
                        <XCircle className="h-6 w-6 text-red-600" />
                        <span className="text-lg font-medium text-red-600">Verification Failed</span>
                    </>
                )}
                {status === 'pending' && (
                    <>
                        <Clock className="h-6 w-6 text-yellow-600" />
                        <span className="text-lg font-medium text-yellow-600">Pending Seal</span>
                    </>
                )}
            </div>

            {/* Hashes */}
            <div className="space-y-3">
                <div>
                    <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Content Hash</dt>
                    <dd className="mt-1 font-mono text-xs text-gray-900 dark:text-gray-100 break-all">
                        {contentHash}
                    </dd>
                </div>

                {signatureHash && (
                    <div>
                        <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            Signature Hash
                        </dt>
                        <dd className="mt-1 font-mono text-xs text-gray-900 dark:text-gray-100 break-all">
                            {signatureHash}
                        </dd>
                    </div>
                )}

                {!signatureHash && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                        Snapshot not yet sealed with cryptographic signature
                    </p>
                )}
            </div>
        </div>
    );
}
