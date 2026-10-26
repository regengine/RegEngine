import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { StepUpModal } from '@/components/auth/StepUpModal';
import { apiClient } from '@/lib/api-client';
import { DEFAULT_STEP_UP_REASON, STEP_UP_REQUIRED_EVENT } from '@/lib/step-up-events';

vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ user: null }) }));

function stepUpResponse(envelope: 'detail' | 'error') {
  return new Response(
    JSON.stringify({
      [envelope]: {
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
  );
}

describe('step-up interceptor', () => {
  const listener = vi.fn();

  beforeEach(() => {
    vi.restoreAllMocks();
    listener.mockReset();
    window.addEventListener(STEP_UP_REQUIRED_EVENT, listener);
  });

  afterEach(() => {
    window.removeEventListener(STEP_UP_REQUIRED_EVENT, listener);
    vi.unstubAllGlobals();
  });

  it('does not prompt when a page-load read returns requires_step_up after a fresh sign in', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stepUpResponse('detail')));
    render(<StepUpModal />);

    await expect(apiClient.getQAHealth()).rejects.toThrow(/forbidden/i);

    expect(listener).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('prompts with the action reason when a write is blocked', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stepUpResponse('detail')));
    render(<StepUpModal />);

    await expect(apiClient.revokeAPIKey(crypto.randomUUID())).rejects.toThrow(/forbidden/i);

    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0][0] as CustomEvent).detail.reason).toBe("Confirm it's you to revoke this API key.");
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveTextContent(/revoke this API key/i));
  });

  it('names the admin policy action when the SSO policy write is blocked', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stepUpResponse('detail')));
    const reason = "Confirm it's you to change your organization's SSO and admin policy.";

    await expect(
      apiClient.updateOrganizationSsoPolicy(
        crypto.randomUUID(),
        { domain_name: 'example.test', domain_verified: false, enforced_auth_policy: 'standard' },
        { stepUpReason: reason },
      ),
    ).rejects.toThrow(/forbidden/i);

    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0][0] as CustomEvent).detail.reason).toBe(reason);
  });

  it('keeps step-up available for a blocked write without a specific action label', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stepUpResponse('detail')));
    render(<StepUpModal />);

    await expect(apiClient.approveReviewItem(crypto.randomUUID())).rejects.toThrow(/forbidden/i);

    expect(listener).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveTextContent(DEFAULT_STEP_UP_REASON));
  });

  it('recognizes the backend structured error envelope on writes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stepUpResponse('error')));

    await expect(apiClient.revokeAPIKey(crypto.randomUUID())).rejects.toThrow(/forbidden/i);

    expect(listener).toHaveBeenCalledTimes(1);
  });
});
