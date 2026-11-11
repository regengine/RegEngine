import { describe, expect, it } from 'vitest';
import {
    latestShipDateInputValue,
    localDateInputValue,
    localDayIsAheadOfUtc,
    utcDateInputValue,
} from '@/lib/local-date';

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

describe('latestShipDateInputValue', () => {
    // A Date is one instant; which calendar day it is depends on the zone the
    // test runs in. These stub the local getters so each case is one zone.
    const at = (utcIso: string, offsetMinutesEast: number): Date => {
        const instant = new Date(utcIso);
        const shifted = new Date(instant.getTime() + offsetMinutesEast * 60_000);
        return Object.assign(new Date(instant.getTime()), {
            getFullYear: () => shifted.getUTCFullYear(),
            getMonth: () => shifted.getUTCMonth(),
            getDate: () => shifted.getUTCDate(),
        });
    };

    it('is the local day for a supplier behind UTC in their evening', () => {
        const losAngeles = at('2026-11-11T02:00:00Z', -480); // 18:00 on the 10th
        expect(latestShipDateInputValue(losAngeles)).toBe('2026-11-10');
        expect(localDayIsAheadOfUtc(losAngeles)).toBe(false);
    });

    it('is the UTC day for a supplier ahead of UTC early in their day', () => {
        const sydney = at('2026-11-10T22:00:00Z', 660); // 09:00 on the 11th
        expect(latestShipDateInputValue(sydney)).toBe('2026-11-10');
        expect(localDayIsAheadOfUtc(sydney)).toBe(true);
    });

    it('is the shared day when local and UTC agree', () => {
        const berlin = at('2026-11-10T12:00:00Z', 60);
        expect(latestShipDateInputValue(berlin)).toBe('2026-11-10');
        expect(localDayIsAheadOfUtc(berlin)).toBe(false);
        expect(utcDateInputValue(new Date('2026-01-05T00:00:00Z'))).toBe('2026-01-05');
    });
});
