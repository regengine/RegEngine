import { describe, expect, it } from 'vitest';
import { inflowErrorMessage } from '@/lib/inflow-error';

describe('Inflow connection errors', () => {
    it('explains an empty disabled-route 404 without claiming the backend is down', () => {
        expect(inflowErrorMessage(404, {})).toContain('Core backend health does not include the simulator');
    });
    it('preserves a specific upstream error', () => {
        expect(inflowErrorMessage(404, { error: 'Fixture missing' })).toBe('Fixture missing');
    });
    it('reports other status failures', () => {
        expect(inflowErrorMessage(502, {})).toBe('Inflow Lab request failed: 502');
    });
});
