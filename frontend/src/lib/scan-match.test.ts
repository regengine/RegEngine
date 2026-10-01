import { describe, expect, it } from 'vitest';

import { parseGS1 } from './gs1-parser';
import { scanMatchesItem, findUniqueScanMatch, type ScanCandidate } from './scan-match';

const ITEM = { gtin: '00614141000012', lotCode: 'TLC-ROM-20260426-001' };

function candidate(raw: string): ScanCandidate {
    // Bare numeric GTIN classification happens before the permissive GS1 parser.
    if (/^\d{8,14}$/.test(raw.trim())) return { raw, gtin: raw.trim() };
    const parsed = parseGS1(raw);
    return { gtin: parsed.gtin, lot: parsed.tlc, raw };
}

describe('scanMatchesItem', () => {
    it('matches a bare GTIN exactly as displayed in the Expected Items list', () => {
        expect(scanMatchesItem(ITEM, candidate('00614141000012'))).toBe(true);
    });

    it('matches a bare lot code exactly as displayed', () => {
        expect(scanMatchesItem(ITEM, candidate('TLC-ROM-20260426-001'))).toBe(true);
    });

    it('matches a GS1 AI-encoded GTIN (AI 01)', () => {
        expect(scanMatchesItem(ITEM, candidate('0100614141000012'))).toBe(true);
    });

    it('matches an AI-encoded GTIN + lot pair against the lot', () => {
        const scan = candidate('010061414100001210TLC-ROM-20260426-001');
        expect(scanMatchesItem({ lotCode: 'TLC-ROM-20260426-001' }, scan)).toBe(true);
    });

    it('tolerates surrounding whitespace on hand-typed input', () => {
        expect(scanMatchesItem(ITEM, candidate('  00614141000012  '))).toBe(true);
    });

    it('rejects an unknown code', () => {
        expect(scanMatchesItem(ITEM, candidate('99999999999999'))).toBe(false);
    });

    it('rejects when the item has no keys to match against', () => {
        expect(scanMatchesItem({}, candidate('00614141000012'))).toBe(false);
    });

    it('never matches on an empty raw string', () => {
        expect(scanMatchesItem(ITEM, { raw: '   ' })).toBe(false);
    });
});

describe('contradictory observations', () => {
 it('rejects matching GTIN with a different observed lot', () => expect(scanMatchesItem(ITEM, { raw: 'encoded', gtin: ITEM.gtin, lot: 'OTHER' })).toBe(false));
 it('rejects matching lot with a different observed GTIN', () => expect(scanMatchesItem(ITEM, { raw: 'encoded', gtin: '99999999999999', lot: ITEM.lotCode })).toBe(false));
});

it('does not auto-select ambiguous shared GTIN rows', () => expect(findUniqueScanMatch([ITEM, { ...ITEM, lotCode: 'OTHER' }], candidate(ITEM.gtin))).toBeUndefined());

it('respects an explicitly classified numeric lot with a different GTIN', () => {
 const scan = { raw: '12345678', lot: '12345678' };
 expect(scanMatchesItem({ gtin: ITEM.gtin, lotCode: '12345678' }, scan)).toBe(true);
 expect(scanMatchesItem({ gtin: '12345678', lotCode: 'OTHER' }, scan)).toBe(false);
});
