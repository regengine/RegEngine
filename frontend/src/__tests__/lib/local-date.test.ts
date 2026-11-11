import { describe, expect, it } from 'vitest';
import { localDateInputValue } from '@/lib/local-date';

describe('localDateInputValue', () => {
    it('uses the local calendar day, not the UTC day', () => {
        // Built from local parts, so the expected local day is known in any TZ.
        const lateEvening = new Date(2026, 10, 9, 23, 30);
        expect(localDateInputValue(lateEvening)).toBe('2026-11-09');
        const justAfterMidnight = new Date(2026, 10, 10, 0, 5);
        expect(localDateInputValue(justAfterMidnight)).toBe('2026-11-10');
    });

    it('zero-pads month and day', () => {
        expect(localDateInputValue(new Date(2026, 0, 5, 12))).toBe('2026-01-05');
    });
});
