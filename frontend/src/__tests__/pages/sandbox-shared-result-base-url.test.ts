import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Regression guard for the 2026-05-14 login outage root cause: the shared
// sandbox result page must build its fetch base URL from NEXT_PUBLIC_SITE_URL
// only, never from VERCEL_URL (the deployment-specific host).

const ORIGINAL_SITE_URL = process.env.NEXT_PUBLIC_SITE_URL;
const ORIGINAL_VERCEL_URL = process.env.VERCEL_URL;

function restore(name: 'NEXT_PUBLIC_SITE_URL' | 'VERCEL_URL', value: string | undefined) {
  if (value === undefined) {
    delete process.env[name];
  } else {
    process.env[name] = value;
  }
}

describe('shared sandbox result base URL resolution', () => {
  beforeEach(() => {
    vi.resetModules();
    delete process.env.NEXT_PUBLIC_SITE_URL;
    delete process.env.VERCEL_URL;
  });

  afterEach(() => {
    restore('NEXT_PUBLIC_SITE_URL', ORIGINAL_SITE_URL);
    restore('VERCEL_URL', ORIGINAL_VERCEL_URL);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  async function renderWithFetchCapture(): Promise<string> {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const mod = await import('@/app/sandbox/results/[id]/page');
    const Page = mod.default;
    await Page({ params: Promise.resolve({ id: 'abc123' }) });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    return fetchMock.mock.calls[0][0] as string;
  }

  it('falls back to localhost when NEXT_PUBLIC_SITE_URL is unset, never VERCEL_URL', async () => {
    process.env.VERCEL_URL = 'regengine-xxxx.vercel.app';

    const url = await renderWithFetchCapture();

    expect(url).toContain('http://localhost:3000/');
    expect(url).not.toContain('regengine-xxxx.vercel.app');
    expect(url).not.toContain('https://undefined');
  });

  it('uses NEXT_PUBLIC_SITE_URL when set, ignoring VERCEL_URL', async () => {
    process.env.NEXT_PUBLIC_SITE_URL = 'https://app.regengine.com';
    process.env.VERCEL_URL = 'regengine-xxxx.vercel.app';

    const url = await renderWithFetchCapture();

    expect(url).toContain('https://app.regengine.com/');
    expect(url).not.toContain('regengine-xxxx.vercel.app');
  });
});
