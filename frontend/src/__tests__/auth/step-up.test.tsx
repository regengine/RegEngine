import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@/lib/api-client';
import { STEP_UP_REQUIRED_EVENT } from '@/lib/step-up-events';

describe('step-up interceptor', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('dispatches a global event for requires_step_up responses', async () => {
    const listener = vi.fn();
    window.addEventListener(STEP_UP_REQUIRED_EVENT, listener);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: 'requires_step_up',
            message: 'High assurance authentication required.',
            auth_method: 'email_otp',
          },
        }),
        {
          status: 403,
          statusText: 'Forbidden',
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    ));

    await expect(apiClient.getAdminHealth()).rejects.toThrow(/forbidden/i);

    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(STEP_UP_REQUIRED_EVENT, listener);
  });

  it('dispatches for the backend structured error envelope', async () => {
    const listener = vi.fn();
    window.addEventListener(STEP_UP_REQUIRED_EVENT, listener);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: 'requires_step_up',
            message: 'High assurance authentication required.',
            auth_method: 'email_otp',
          },
        }),
        {
          status: 403,
          statusText: 'Forbidden',
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    ));

    await expect(apiClient.getAdminHealth()).rejects.toThrow(/forbidden/i);

    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener(STEP_UP_REQUIRED_EVENT, listener);
  });
});
