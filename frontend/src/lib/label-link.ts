import { isValidGTINCheckDigit } from './gs1-parser';

/**
 * Label QR landing: /01/{gtin}/10/{lot}/21/{serial}
 *
 * services/graph/app/routers/labels.py prints this GS1 Digital Link path on
 * every label it issues (generate_qr_payload), with the lot quoted as
 * urllib.parse.quote(lot, safe="") so a slash travels as %2F.
 *
 * How Next 16.4.2 hands the segments over (node_modules/next/dist):
 * shared/lib/router/utils/route-matcher.js:19 decodes each matched segment
 * once; shared/lib/router/utils/get-dynamic-param.js:58 then re-encodes it
 * with encodeURIComponent for the page's `params`, while
 * lib/metadata/resolve-metadata.js:173 passes the decoded value straight
 * to generateMetadata. So the page decodes exactly once and
 * generateMetadata must not decode at all (`alreadyDecoded`).
 *
 * On Vercel the router decodes the path once more before Next sees it
 * (measured on the preview: /10/100%252F/ renders "100/" and /10/A%2525B/
 * renders "A%B" on both the page and the title; locally the same URLs
 * decode once). A lot without a literal "%" is unaffected, and %2F itself
 * routes as one segment. A lot that does contain a literal escape loses it
 * before this code runs, so labels.py rejects a "%" in lot_number at
 * issuance (TraceabilityInfo.validate_lot_number_scannable) instead.
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

export interface LabelLink {
    gtin: string;
    lot: string;
    serial: string;
    gtinCheckDigitValid: boolean;
}

/** Null when the segments cannot have come from a RegEngine label. */
export function parseLabelLink(
    segments: { gtin?: string; lot?: string; serial?: string },
    { alreadyDecoded = false }: { alreadyDecoded?: boolean } = {},
): LabelLink | null {
    const decode = alreadyDecoded ? (v: string) => v : decodeSegment;
    const gtin = decode(segments.gtin ?? '');
    const lot = decode(segments.lot ?? '');
    const serial = decode(segments.serial ?? '');

    // labels.py validates the GTIN as exactly 14 digits but not its check
    // digit, so a bad check digit is reported, not rejected.
    if (!/^\d{14}$/.test(gtin)) return null;
    // labels.py caps neither the lot nor the serial, so neither is capped
    // here: a cap would 404 a label that has already been printed.
    if (!lot || !serial) return null;

    return { gtin, lot, serial, gtinCheckDigitValid: isValidGTINCheckDigit(gtin) };
}

export function traceHrefForLot(lot: string): string {
    return `/trace?tlc=${encodeURIComponent(lot)}`;
}
