/// <reference types="vitest/jsdom" />
/**
 * Gating for the 9 gap tool_ids uses the real provider: cookieless capture
 * before Accept is kept, and Decline sends nothing.
 */
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const sdk = vi.hoisted(() => ({
  imported: vi.fn(),
  client: {
    init: vi.fn(),
    capture: vi.fn(),
    has_opted_out_capturing: vi.fn(() => false),
    opt_in_capturing: vi.fn(),
    opt_out_capturing: vi.fn(),
    set_config: vi.fn(),
    identify: vi.fn(),
  },
}));

const navigation = vi.hoisted(() => ({ pathname: '/tools/scan', search: '' }));

vi.mock('posthog-js', () => {
  sdk.imported();
  return { default: sdk.client };
});

vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  sdk.client.has_opted_out_capturing.mockReturnValue(false);
  vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
  vi.stubEnv('NEXT_PUBLIC_POSTHOG_HOST', undefined);
  vi.stubEnv('NEXT_PUBLIC_POSTHOG_ALLOW_LOCALHOST', undefined);
  jsdom.reconfigure({ url: 'https://regengine.co/tools/scan' });
  document.cookie = 're_cookie_consent=; max-age=0; path=/';
  window.localStorage.removeItem('re_internal');
  window.history.replaceState({}, '', '/tools/scan');
  navigation.pathname = '/tools/scan';
  navigation.search = '';
});

describe('gap tool_started gating', () => {
  it('keeps cookieless capture before Accept for a gap tool_id', async () => {
    const { captureEvent, CSPostHogProvider } = await import('@/lib/posthog-provider');
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    captureEvent('tool_started', { tool_id: 'ask' });

    await waitFor(() => expect(sdk.client.init).toHaveBeenCalledTimes(1));
    const options = sdk.client.init.mock.calls[0][1] as { persistence: string };
    expect(options.persistence).toBe('memory');
    await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledWith('tool_started', { tool_id: 'ask' }));
    expect(sdk.client.opt_in_capturing).not.toHaveBeenCalled();
  });

  it('sends nothing for gap tool_ids after Decline, including on a later page load', async () => {
    document.cookie = 're_cookie_consent=declined; path=/';
    const first = await import('@/lib/posthog-provider');
    render(<first.CSPostHogProvider>content</first.CSPostHogProvider>);
    first.captureEvent('tool_started', { tool_id: 'scan' });
    first.captureEvent('tool_started', { tool_id: 'self-reported-checklist' });

    // A later page load: fresh module state, same stored choice.
    vi.resetModules();
    const reload = await import('@/lib/posthog-provider');
    render(<reload.CSPostHogProvider>content</reload.CSPostHogProvider>);
    reload.captureEvent('tool_started', { tool_id: 'drill-simulator' });

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(sdk.imported).not.toHaveBeenCalled();
    expect(sdk.client.init).not.toHaveBeenCalled();
    expect(sdk.client.capture).not.toHaveBeenCalled();
  });
});
