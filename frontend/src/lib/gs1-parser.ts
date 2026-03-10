/**
 * GS1-128 Barcode Parser
 *
 * Extracts Application Identifiers (AIs) from a raw GS1 barcode string.
 * Common AIs:
 * (01) - GTIN (14 digits)
 * (10) - Batch/Lot Number (Variable length, up to 20 chars)
 * (13) - Packaging date (YYMMDD)
 * (17) - Expiration date (YYMMDD)
 * (21) - Serial number (Variable length, up to 20 chars)
 */

export interface GS1ParsedData {
    gtin?: string;
    tlc?: string;
    serial?: string;
    packDate?: string;
    expiryDate?: string;
    sourceFormat?: 'gs1_ai' | 'digital_link' | 'unknown';
    isValidGTIN?: boolean;
    raw: string;
}

const GROUP_SEPARATOR = String.fromCharCode(29);
const AI_FIXED_LENGTH: Record<string, number> = {
    '01': 14,
    '13': 6,
    '17': 6,
};
const AI_VARIABLE = new Set(['10', '21']);
const AI_SUPPORTED = new Set([
    ...Object.keys(AI_FIXED_LENGTH),
    ...Array.from(AI_VARIABLE),
]);

function normalizeInput(raw: string): string {
    return raw
        .trim()
        .replace(/\s+/g, '')
        .replace(/[()]/g, '')
        .replace(/\u00f1/gi, GROUP_SEPARATOR); // scanner FNC1 surrogate
}

function parseYYMMDD(value?: string): string | undefined {
    if (!value || !/^\d{6}$/.test(value)) return undefined;

    const year = 2000 + Number(value.slice(0, 2));
    const month = Number(value.slice(2, 4));
    const day = Number(value.slice(4, 6));
    if (month < 1 || month > 12 || day < 1 || day > 31) return undefined;

    const date = new Date(Date.UTC(year, month - 1, day));
    if (
        date.getUTCFullYear() !== year ||
        date.getUTCMonth() !== month - 1 ||
        date.getUTCDate() !== day
    ) {
        return undefined;
    }

    const mm = String(month).padStart(2, '0');
    const dd = String(day).padStart(2, '0');
    return `${year}-${mm}-${dd}`;
}

function maybeKnownAiAt(input: string, index: number): boolean {
    const ai = input.slice(index, index + 2);
    if (!AI_SUPPORTED.has(ai)) return false;
    if (ai in AI_FIXED_LENGTH) {
        return index + 2 + AI_FIXED_LENGTH[ai] <= input.length;
    }
    return index + 2 <= input.length;
}

function findNextFieldBoundary(input: string, from: number): number {
    for (let i = from; i < input.length; i += 1) {
        if (input[i] === GROUP_SEPARATOR) return i;
        if (maybeKnownAiAt(input, i)) return i;
    }
    return input.length;
}

function parseDigitalLink(raw: string): Partial<GS1ParsedData> | null {
    const trimmed = raw.trim();
    if (!trimmed) return null;

    let path = '';
    if (/^https?:\/\//i.test(trimmed)) {
        try {
            const parsed = new URL(trimmed);
            path = parsed.pathname;
        } catch {
            return null;
        }
    } else if (trimmed.startsWith('/')) {
        path = trimmed.split('?')[0].split('#')[0];
    } else {
        return null;
    }

    const segments = path.split('/').filter(Boolean);
    if (!segments.includes('01')) return null;

    const fields: Partial<GS1ParsedData> = {};
    for (let i = 0; i < segments.length - 1; i += 1) {
        const ai = segments[i];
        const value = decodeURIComponent(segments[i + 1]);
        if (!value) continue;

        if (ai === '01' && !fields.gtin) fields.gtin = value;
        if (ai === '10' && !fields.tlc) fields.tlc = value;
        if (ai === '21' && !fields.serial) fields.serial = value;
        if (ai === '13' && !fields.packDate) fields.packDate = parseYYMMDD(value);
        if (ai === '17' && !fields.expiryDate) fields.expiryDate = parseYYMMDD(value);
    }

    if (!fields.gtin && !fields.tlc && !fields.serial) return null;

    fields.sourceFormat = 'digital_link';
    return fields;
}

export function isValidGTINCheckDigit(gtin: string): boolean {
    if (!/^\d{14}$/.test(gtin)) return false;

    const digits = gtin.split('').map((digit) => Number(digit));
    const checkDigit = digits[13];

    let sum = 0;
    let weight = 3;
    for (let i = 12; i >= 0; i -= 1) {
        sum += digits[i] * weight;
        weight = weight === 3 ? 1 : 3;
    }

    const expectedCheckDigit = (10 - (sum % 10)) % 10;
    return expectedCheckDigit === checkDigit;
}

export function parseGS1(raw: string): GS1ParsedData {
    const data: GS1ParsedData = {
        raw,
        sourceFormat: 'unknown',
    };

    const digitalLinkData = parseDigitalLink(raw);
    if (digitalLinkData) {
        Object.assign(data, digitalLinkData);
    } else {
        const working = normalizeInput(raw);
        let index = 0;
        data.sourceFormat = 'gs1_ai';

        while (index < working.length) {
            if (working[index] === GROUP_SEPARATOR) {
                index += 1;
                continue;
            }

            const ai = working.slice(index, index + 2);
            if (!AI_SUPPORTED.has(ai)) {
                index += 1;
                continue;
            }

            if (ai in AI_FIXED_LENGTH) {
                const length = AI_FIXED_LENGTH[ai];
                const value = working.slice(index + 2, index + 2 + length);
                if (value.length === length) {
                    if (ai === '01' && !data.gtin) data.gtin = value;
                    if (ai === '13' && !data.packDate) data.packDate = parseYYMMDD(value);
                    if (ai === '17' && !data.expiryDate) data.expiryDate = parseYYMMDD(value);
                }
                index += 2 + length;
                continue;
            }

            const start = index + 2;
            const end = findNextFieldBoundary(working, start);
            const value = working.slice(start, end);
            if (value) {
                if (ai === '10' && !data.tlc) data.tlc = value;
                if (ai === '21' && !data.serial) data.serial = value;
            }
            index = end;
        }
    }

    if (data.gtin) {
        data.isValidGTIN = isValidGTINCheckDigit(data.gtin);
    }

    return data;
}

/**
 * Validates if the capture looks like a valid FSMA-relevant barcode
 */
export function isFSMACompatible(data: GS1ParsedData): boolean {
    return !!(data.tlc || (data.gtin && data.isValidGTIN !== false));
}
