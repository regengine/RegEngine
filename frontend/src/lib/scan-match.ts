/**
 * Receiving-dock scan matching.
 *
 * A scan can arrive as a GS1 AI-encoded string / GS1 Digital Link (parsed
 * upstream by parseGS1) or as a bare GTIN / lot code typed by hand — the
 * Expected Items list displays bare values and the scan input invites
 * typing them, so the raw string must count as a match candidate too.
 * Extracted from the receiving page so the matrix is unit-testable.
 */

export interface ScanCandidate {
    /** GTIN extracted by parseGS1, if the input was AI-encoded. */
    gtin?: string;
    /** Lot/TLC extracted by parseGS1, if the input was AI-encoded. */
    lot?: string;
    /** The raw scanned/typed string. */
    raw: string;
}

export interface ExpectedItemKeys {
    gtin?: string;
    lotCode?: string;
}

export function scanMatchesItem(item: ExpectedItemKeys, scan: ScanCandidate): boolean {
    const raw = scan.raw.trim();
    if (item.gtin && scan.gtin && item.gtin !== scan.gtin) return false;
    if (item.lotCode && scan.lot && item.lotCode !== scan.lot) return false;
    const hasExplicitIdentifier = Boolean(scan.gtin || scan.lot);
    const gtinMatch = Boolean(item.gtin && scan.gtin && item.gtin === scan.gtin) ||
        Boolean(!hasExplicitIdentifier && item.gtin && raw && item.gtin === raw);
    const lotMatch = Boolean(item.lotCode && scan.lot && item.lotCode === scan.lot) ||
        Boolean(!hasExplicitIdentifier && item.lotCode && raw && item.lotCode === raw);
    return gtinMatch || lotMatch;
}

/** A shared identifier is insufficient when multiple expected rows qualify. */
export function findUniqueScanMatch<T extends ExpectedItemKeys>(items: T[], scan: ScanCandidate): T | undefined {
    const matches = items.filter(item => scanMatchesItem(item, scan));
    return matches.length === 1 ? matches[0] : undefined;
}
