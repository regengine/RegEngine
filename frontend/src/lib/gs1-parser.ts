/**
 * GS1-128 Barcode Parser
 * 
 * Extracts Application Identifiers (AIs) from a raw GS1 barcode string.
 * Common AIs:
 * (01) - GTIN (14 digits)
 * (10) - Batch/Lot Number (Variable length, up to 20 chars)
 */

export interface GS1ParsedData {
    gtin?: string;
    tlc?: string;
    raw: string;
}

export function parseGS1(raw: string): GS1ParsedData {
    const data: GS1ParsedData = { raw };

    // Normalize input (remove brackets, handle standard separators)
    // Some scanners return brackets (01)GTIN, others return literal 01GTIN
    let working = raw.replace(/[()]/g, '');

    // GS1-128 is a concatenated string of [AI][Value]
    // AI 01 (GTIN) is fixed length 14
    if (working.startsWith('01')) {
        data.gtin = working.substring(2, 16);
        working = working.substring(16);
    } else if (working.includes('01') && working.indexOf('01') < 5) {
        // Handle cases where 01 might not be the absolute start due to prefixing
        const idx = working.indexOf('01');
        data.gtin = working.substring(idx + 2, idx + 16);
    }

    // AI 10 (Batch/Lot) is variable length, often followed by other AIs or the end
    // For our Field Companion, we look for '10' as a prefix or internal marker
    if (working.startsWith('10')) {
        data.tlc = working.substring(2);
    } else {
        // Regex fallback for identifying (10) or literal 10 followed by alphanumeric
        const lotMatch = working.match(/10([A-Z0-9-]{4,20})/);
        if (lotMatch) {
            data.tlc = lotMatch[1];
        }
    }

    return data;
}

/**
 * Validates if the capture looks like a valid FSMA-relevant barcode
 */
export function isFSMACompatible(data: GS1ParsedData): boolean {
    return !!(data.tlc || data.gtin);
}
