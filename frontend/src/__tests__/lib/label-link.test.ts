import { describe, expect, it } from 'vitest';
import { parseLabelLink, traceHrefForLot } from '@/lib/label-link';

// GTIN-14 with a correct check digit (mod-10, weights 3/1 from the right).
const VALID_GTIN = '00012345678905';
const SERIAL = '000123456789012345'; // SSCC-18, what labels.py puts in AI 21

describe('parseLabelLink', () => {
    it('accepts the segments labels.py prints and reports a valid check digit', () => {
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'LOT-2026-SAL-0001', serial: SERIAL })).toEqual({
            gtin: VALID_GTIN,
            lot: 'LOT-2026-SAL-0001',
            serial: SERIAL,
            gtinCheckDigitValid: true,
        });
    });

    it('decodes the raw segment the page component receives', () => {
        // What labels.py printed for lot "LOT-2024/001", as Next hands it to page.tsx.
        // The "%"-bearing lots below exercise decode-once behaviour for hand-typed
        // URLs; labels.py refuses to print a lot containing "%".
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'LOT-2024%2F001', serial: SERIAL })?.lot).toBe('LOT-2024/001');
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'A%25B', serial: SERIAL })?.lot).toBe('A%B');
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'A%20B', serial: SERIAL })?.lot).toBe('A B');
    });

    it('decodes exactly once: a lot that itself contains an escape keeps it', () => {
        // Lot "100%2F" prints as /10/100%252F/ and reaches page.tsx re-encoded.
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: '100%252F', serial: SERIAL })?.lot).toBe('100%2F');
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'A%252FB', serial: SERIAL })?.lot).toBe('A%2FB');
    });

    it('does not decode when told the segments are already decoded, as generateMetadata gets them', () => {
        const opts = { alreadyDecoded: true };
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'LOT-2024/001', serial: SERIAL }, opts)?.lot).toBe('LOT-2024/001');
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'A%2FB', serial: SERIAL }, opts)?.lot).toBe('A%2FB');
    });

    it('keeps a segment with a broken escape instead of throwing', () => {
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: '100%', serial: SERIAL })?.lot).toBe('100%');
    });

    it('reports a wrong check digit instead of rejecting the label', () => {
        // labels.py only checks for 14 digits, so a real label can carry this.
        const link = parseLabelLink({ gtin: '00012345678901', lot: 'L1', serial: SERIAL });
        expect(link).not.toBeNull();
        expect(link?.gtinCheckDigitValid).toBe(false);
    });

    it('rejects a GTIN that is not exactly 14 digits', () => {
        expect(parseLabelLink({ gtin: '0001234567890', lot: 'L1', serial: SERIAL })).toBeNull();
        expect(parseLabelLink({ gtin: '000123456789050', lot: 'L1', serial: SERIAL })).toBeNull();
        expect(parseLabelLink({ gtin: '0001234567890X', lot: 'L1', serial: SERIAL })).toBeNull();
        expect(parseLabelLink({ lot: 'L1', serial: SERIAL })).toBeNull();
    });

    it('rejects an empty lot or serial but no length the label service can print', () => {
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: '', serial: SERIAL })).toBeNull();
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'L1', serial: '' })).toBeNull();
        // labels.py caps neither field; a printed label must never 404 here.
        // Far beyond any cap a reviewer might reintroduce.
        const long = 'x'.repeat(5000);
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: long, serial: SERIAL })?.lot).toBe(long);
        expect(parseLabelLink({ gtin: VALID_GTIN, lot: 'L1', serial: long })?.serial).toBe(long);
    });
});

describe('traceHrefForLot', () => {
    it('encodes the lot so a slash survives the query string', () => {
        expect(traceHrefForLot('LOT-2024/001')).toBe('/trace?tlc=LOT-2024%2F001');
    });
});
