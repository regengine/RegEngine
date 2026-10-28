/// <reference types="vitest/jsdom" />
/**
 * SEL-585 F1, A-2138: with the real posthog-js SDK, a visitor who has not accepted
 * cookies gets no cookie, localStorage or sessionStorage entries, and no identify call.
 */
import { waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));

beforeEach(() => {
  vi.resetModules();
  vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
  vi.stubGlobal('fetch', fetchMock);
  jsdom.reconfigure({ url: 'https://regengine.co/tools/ftl-checker' });
  for (const cookie of document.cookie.split(';')) {
    const name = cookie.split('=')[0].trim();
    if (name) document.cookie = `${name}=; max-age=0; path=/`;
  }
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  jsdom.reconfigure({ url: 'http://localhost:3000/' });
});

describe('cookieless PostHog before consent (real SDK)', () => {
  it('writes no cookie or storage and never identifies', async () => {
    const posthog = (await import('posthog-js')).default;
    const identify = vi.spyOn(posthog, 'identify');
    const init = vi.spyOn(posthog, 'init');
    const { captureEvent } = await import('@/lib/posthog-provider');

    captureEvent('tool_started', { tool_id: 'ftl-checker' });
    await waitFor(() => expect(init).toHaveBeenCalledTimes(1));
    captureEvent('tool_completed', { tool_id: 'ftl-checker', status: 'success' });

    expect(document.cookie).toBe('');
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(identify).not.toHaveBeenCalled();
  });
});
