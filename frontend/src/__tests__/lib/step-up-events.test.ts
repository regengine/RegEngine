import { describe, expect, it, vi } from 'vitest';

import {
    STEP_UP_REQUIRED_EVENT,
    emitStepUpRequired,
    isRequiresStepUpPayload,
} from '@/lib/step-up-events';

describe('isRequiresStepUpPayload', () => {
    it('recognizes the step-up code at the top level, in detail and in error', () => {
        expect(isRequiresStepUpPayload({ code: 'requires_step_up' })).toBe(true);
        expect(isRequiresStepUpPayload({ detail: { code: 'requires_step_up' } })).toBe(true);
        expect(isRequiresStepUpPayload({ error: { code: 'requires_step_up' } })).toBe(true);
    });

    it('rejects other codes, arrays, primitives and null', () => {
        expect(isRequiresStepUpPayload({ code: 'forbidden' })).toBe(false);
        expect(isRequiresStepUpPayload({ detail: { code: 'forbidden' } })).toBe(false);
        expect(isRequiresStepUpPayload([{ code: 'requires_step_up' }])).toBe(false);
        expect(isRequiresStepUpPayload(null)).toBe(false);
        expect(isRequiresStepUpPayload('requires_step_up')).toBe(false);
    });
});

describe('emitStepUpRequired', () => {
    it('dispatches the step-up event carrying the backend payload', () => {
        const listener = vi.fn();
        window.addEventListener(STEP_UP_REQUIRED_EVENT, listener);
        try {
            const payload = { detail: { code: 'requires_step_up' } };
            emitStepUpRequired(payload);
            expect(listener).toHaveBeenCalledTimes(1);
            expect((listener.mock.calls[0][0] as CustomEvent).detail).toBe(payload);
        } finally {
            window.removeEventListener(STEP_UP_REQUIRED_EVENT, listener);
        }
    });

    it('stays silent for payloads that do not require step-up', () => {
        const listener = vi.fn();
        window.addEventListener(STEP_UP_REQUIRED_EVENT, listener);
        try {
            emitStepUpRequired({ detail: 'plain 403' });
            expect(listener).not.toHaveBeenCalled();
        } finally {
            window.removeEventListener(STEP_UP_REQUIRED_EVENT, listener);
        }
    });
});
