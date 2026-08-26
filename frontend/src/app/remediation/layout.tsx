import { notFound } from 'next/navigation';

/**
 * Remediation remains outside the approved production router inventory.
 *
 * Keep the dormant page implementation available for a future reviewed
 * promotion, but make the current UI surface indistinguishable from an absent
 * route. The ingestion BFF independently enforces the same exact-404 boundary.
 */
export default function RemediationLayout(): never {
    notFound();
}
