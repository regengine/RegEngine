import { describe, expect, it, vi } from 'vitest';

const { notFoundMock, notFoundSignal } = vi.hoisted(() => {
    const signal = new Error('NEXT_NOT_FOUND');
    return {
        notFoundSignal: signal,
        notFoundMock: vi.fn((): never => {
            throw signal;
        }),
    };
});

vi.mock('next/navigation', () => ({ notFound: notFoundMock }));

import RemediationLayout from '@/app/remediation/layout';

describe('remediation UI release gate', () => {
    it('resolves the production page as not found before rendering its children', () => {
        expect(() => RemediationLayout()).toThrow(notFoundSignal);
        expect(notFoundMock).toHaveBeenCalledTimes(1);
    });
});
