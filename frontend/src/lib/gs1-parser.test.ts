import { describe, it, expect } from 'vitest';
import { isValidGTINCheckDigit, parseGS1 } from './gs1-parser';

describe('GS1-128 Parser', () => {
    it('should parse a standard GS1-128 with brackets', () => {
        const raw = "(01)10614141000019(10)TLC-3489";
        const result = parseGS1(raw);
        expect(result.gtin).toBe("10614141000019");
        expect(result.tlc).toBe("TLC-3489");
        expect(result.sourceFormat).toBe("gs1_ai");
        expect(result.isValidGTIN).toBe(true);
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
        expect(result.isValidGTIN).toBe(true);
    });

    it('should handle barcodes with only TLC (fallback match)', () => {
        const raw = "10TLC-9999";
        const result = parseGS1(raw);
        expect(result.tlc).toBe("TLC-9999");
    });

    it('should parse AI 17 (expiry), AI 13 (pack date), and AI 21 (serial)', () => {
        const raw = "(01)10614141000019(17)260930(13)260801(21)SN-4458";
        const result = parseGS1(raw);

        expect(result.gtin).toBe("10614141000019");
        expect(result.expiryDate).toBe("2026-09-30");
        expect(result.packDate).toBe("2026-08-01");
        expect(result.serial).toBe("SN-4458");
    });

    it('should parse AI fields separated by GS separator characters', () => {
        const raw = `011061414100001910LOT-99${String.fromCharCode(29)}1726093021SER-9`;
        const result = parseGS1(raw);

        expect(result.gtin).toBe("10614141000019");
        expect(result.tlc).toBe("LOT-99");
        expect(result.expiryDate).toBe("2026-09-30");
        expect(result.serial).toBe("SER-9");
    });

    it('should parse GS1 Digital Link URLs', () => {
        const raw = "https://id.example.com/01/09506000134352/10/LOT-2026-44/21/SER-778/17/260930";
        const result = parseGS1(raw);

        expect(result.sourceFormat).toBe("digital_link");
        expect(result.gtin).toBe("09506000134352");
        expect(result.tlc).toBe("LOT-2026-44");
        expect(result.serial).toBe("SER-778");
        expect(result.expiryDate).toBe("2026-09-30");
        expect(result.isValidGTIN).toBe(true);
    });

    it('should parse GS1 Digital Link path-only payloads', () => {
        const raw = "/01/09506000134352/10/LOT%2FALPHA/21/SN-001";
        const result = parseGS1(raw);

        expect(result.sourceFormat).toBe("digital_link");
        expect(result.gtin).toBe("09506000134352");
        expect(result.tlc).toBe("LOT/ALPHA");
        expect(result.serial).toBe("SN-001");
    });
});

describe('GTIN check digit validation', () => {
    it('accepts valid GTIN-14 values', () => {
        expect(isValidGTINCheckDigit("09506000134352")).toBe(true);
        expect(isValidGTINCheckDigit("10614141000019")).toBe(true);
    });

    it('rejects invalid GTIN-14 values', () => {
        expect(isValidGTINCheckDigit("09506000134359")).toBe(false);
        expect(isValidGTINCheckDigit("10614141000011")).toBe(false);
        expect(isValidGTINCheckDigit("ABC9506000134352")).toBe(false);
    });
});
