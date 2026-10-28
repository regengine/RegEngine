import { isValidGTINCheckDigit } from './gs1-parser';

/**
 * Label QR landing: /01/{gtin}/10/{lot}/21/{serial}
 *
 * services/graph/app/routers/labels.py prints this GS1 Digital Link path on
 * every label it issues (generate_qr_payload), with the lot quoted as
 * urllib.parse.quote(lot, safe="") so a slash travels as %2F.
 *
 * Measured on Next 16.4.2: the page component receives the segments raw
 * (LOT-2024%2F001) while generateMetadata receives them decoded
 * (LOT-2024/001). decodeSegment decodes once and is a no-op on an already
 * decoded value, so both callers get the same answer. The one gap: a lot
 * that itself contains a literal escape sequence (100%2F) decodes twice on
 * the metadata path and shows as 100/ in the tab title only.
 */

function decodeSegment(value: string): string {
    try {
        return decodeURIComponent(value);
    } catch {
        // A bare % or a broken escape is not something labels.py emits; keep
        // it as-is so the page can still show what was scanned.
        return value;
    }
}

/** GS1 AI 10 and 21 allow 20 characters; labels.py does not cap the lot, so
 *  the bound is loose and only rejects junk that no label could carry. */
export const LABEL_FIELD_MAX_LENGTH = 64;

export interface LabelLink {
    gtin: string;
    lot: string;
    serial: string;
    gtinCheckDigitValid: boolean;
}

/** Null when the segments cannot have come from a RegEngine label. */
export function parseLabelLink(segments: { gtin?: string; lot?: string; serial?: string }): LabelLink | null {
    const gtin = decodeSegment(segments.gtin ?? '');
    const lot = decodeSegment(segments.lot ?? '');
    const serial = decodeSegment(segments.serial ?? '');

    // labels.py validates the GTIN as exactly 14 digits but not its check
    // digit, so a bad check digit is reported, not rejected.
    if (!/^\d{14}$/.test(gtin)) return null;
    if (!lot || lot.length > LABEL_FIELD_MAX_LENGTH) return null;
    if (!serial || serial.length > LABEL_FIELD_MAX_LENGTH) return null;

    return { gtin, lot, serial, gtinCheckDigitValid: isValidGTINCheckDigit(gtin) };
}

export function traceHrefForLot(lot: string): string {
    return `/trace?tlc=${encodeURIComponent(lot)}`;
}
