/** Describe only coverage returned by the verifier; never infer a seal scope. */
export function SnapshotIntegrityCoverage({ version, coverage }: { version?: number | null; coverage?: string | null }) {
    return (
        <p className="text-ui text-re-text-secondary">
            Hash version: {version ?? 'unknown'}. Coverage: {coverage ?? 'not provided; full snapshot integrity is not established'}.
        </p>
    );
}
