import { describe, it, expect } from 'vitest';
import { parseGS1 } from './gs1-parser';

describe('GS1-128 Parser', () => {
    it('should parse a standard GS1-128 with brackets', () => {
        const raw = "(01)10614141000019(10)TLC-3489";
        const result = parseGS1(raw);
        expect(result.gtin).toBe("10614141000019");
        expect(result.tlc).toBe("TLC-3489");
    });

    it('should parse a literal GS1-128 without brackets', () => {
        const raw = "011061414100001910LOT-BETA-77";
        const result = parseGS1(raw);
        expect(result.gtin).toBe("10614141000019");
        expect(result.tlc).toBe("LOT-BETA-77");
    });

    it('should handle barcodes with only GTIN', () => {
        const raw = "0110614141000019";
        const result = parseGS1(raw);
        expect(result.gtin).toBe("10614141000019");
        expect(result.tlc).toBeUndefined();
    });

    it('should handle barcodes with only TLC (fallback match)', () => {
        const raw = "10TLC-9999";
        const result = parseGS1(raw);
        expect(result.tlc).toBe("TLC-9999");
    });
});
