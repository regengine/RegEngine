import { describe, expect, it } from 'vitest';
import { isValidGTINCheckDigit, parseGS1 } from '@/lib/gs1-parser';

describe('2026-10-02 QA: GS1 traceability input boundaries', () => {
    it('keeps Digital Link lot values intact across encoded delimiters', () => {
        for (const lot of ['LOT-10', 'LOT-21', 'LOT/ALPHA', 'LOT%PERCENT', 'LOT A']) {
            const parsed = parseGS1(`/01/09506000134352/10/${encodeURIComponent(lot)}`);
            expect(parsed.tlc).toBe(lot);
            expect(parsed.isValidGTIN).toBe(true);
        }
    });

    it('checks every possible check digit for 100 generated GTIN bodies', () => {
        for (let index = 0; index < 100; index += 1) {
            const body = String(950600010000 + index).padStart(13, '0');
            const weightedSum = [...body].reduce(
                (total, digit, position) => total + Number(digit) * (position % 2 === 0 ? 3 : 1),
                0,
            );
            const expected = (10 - weightedSum % 10) % 10;
            for (let candidate = 0; candidate < 10; candidate += 1) {
                expect(isValidGTINCheckDigit(`${body}${candidate}`)).toBe(candidate === expected);
            }
        }
    });

    it.each(['260230', '260431', '261300', '260000'])('rejects impossible calendar date %s', (value) => {
        expect(parseGS1(`(01)09506000134352(17)${value}`).expiryDate).toBeUndefined();
    });

    // FE-001: a variable-length lot ends only at its explicit delimiter/end.
    // Existing parser wrongly treats AI-like digits inside the lot as a new AI.
    it.each(['LOT-10-ABC', 'LOT-21-ABC', 'LOT-17260930'])('FE-001 preserves lot %s through the group separator', (lot) => {
        const input = `010950600013435210${lot}\x1d17260930`;
        const parsed = parseGS1(input);
        expect(parsed.tlc).toBe(lot);
        expect(parsed.expiryDate).toBe('2026-09-30');
    });

    // FE-002: invalid percent encodings must become a rejected scan, not an
    // uncaught URIError in receiving, field capture, or the public scanner.
    it.fails.each(['%', '%ZZ', '%E0%A4'])('FE-002 handles malformed Digital Link escape %s without throwing', (lot) => {
        expect(() => parseGS1(`/01/09506000134352/10/${lot}`)).not.toThrow();
    });
});
