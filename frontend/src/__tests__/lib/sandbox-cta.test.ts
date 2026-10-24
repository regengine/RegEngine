import { describe, it, expect } from 'vitest';
import { sandboxCta } from '@/lib/sandbox-cta';

describe('sandboxCta', () => {
    it('points at the CSV upload route, never the retired /sandbox or /demo', () => {
        const cta = sandboxCta();
        expect(cta.href).toBe('/ingest');
        expect(cta.href).not.toBe('/sandbox');
        expect(cta.href).not.toBe('/demo');
    });
});
