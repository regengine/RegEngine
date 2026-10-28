/// <reference types="vitest/jsdom" />
import { render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

const navigation = vi.hoisted(() => ({ pathname: '/tools/ftl-checker', search: '' }));

vi.mock('posthog-js', () => {
  sdk.imported();
  return { default: sdk.client };
});

vi.mock('next/navigation', () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(navigation.search),
}));

let originalSendBeacon: PropertyDescriptor | undefined;
let originalReferrer: PropertyDescriptor | undefined;
const sendBeacon = vi.fn();

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  sdk.client.has_opted_out_capturing.mockReturnValue(false);
  vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', 'phc_test');
  vi.stubEnv('NEXT_PUBLIC_POSTHOG_HOST', undefined);
  vi.stubEnv('NEXT_PUBLIC_POSTHOG_ALLOW_LOCALHOST', undefined);
  jsdom.reconfigure({ url: 'https://regengine.co/tools/ftl-checker' });
  document.cookie = 're_cookie_consent=; max-age=0; path=/';
  window.localStorage.removeItem('re_internal');
  window.history.replaceState({}, '', '/tools/ftl-checker');
  navigation.pathname = '/tools/ftl-checker';
  navigation.search = '';
  originalReferrer = Object.getOwnPropertyDescriptor(document, 'referrer');
  originalSendBeacon = Object.getOwnPropertyDescriptor(navigator, 'sendBeacon');
  Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: sendBeacon });
});

afterEach(() => {
  vi.unstubAllEnvs();
  jsdom.reconfigure({ url: 'http://localhost:3000/' });
  if (originalReferrer) {
    Object.defineProperty(document, 'referrer', originalReferrer);
  } else {
    Reflect.deleteProperty(document, 'referrer');
  }
  if (originalSendBeacon) {
    Object.defineProperty(navigator, 'sendBeacon', originalSendBeacon);
  } else {
    Reflect.deleteProperty(navigator, 'sendBeacon');
  }
});

async function providerModule() {
  return import('@/lib/posthog-provider');
}

async function initializedOptions() {
  await waitFor(() => expect(sdk.client.init).toHaveBeenCalledTimes(1));
  return sdk.client.init.mock.calls[0][1] as {
    api_host: string;
    autocapture: boolean;
    capture_pageview: boolean;
    disable_session_recording: boolean;
    persistence: string;
    before_send: (event: {
      event: string;
      properties: Record<string, unknown>;
      $set?: Record<string, unknown>;
      $set_once?: Record<string, unknown>;
      $unset?: string[];
    }) => {
      event: string;
      properties: Record<string, unknown>;
      $set?: Record<string, unknown>;
      $set_once?: Record<string, unknown>;
      $unset?: string[];
    } | null;
  };
}

describe('PostHog client initialization', () => {
  it.each([undefined, 'phc_placeholder'])('does not load the SDK without a usable key (%s)', async (key) => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_KEY', key);
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { captureEvent, CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    captureEvent('tool_started', { tool_id: 'ftl-checker' });
    await waitFor(() => expect(sdk.client.init).not.toHaveBeenCalled());
    expect(sdk.imported).not.toHaveBeenCalled();
    expect(sdk.client.capture).not.toHaveBeenCalled();
  });

  it('runs cookieless before consent: memory persistence, no opt-in record, no identify', async () => {
    const { captureEvent, CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    captureEvent('tool_started', { tool_id: 'ftl-checker' });
    const options = await initializedOptions();
    expect(options.persistence).toBe('memory');
    await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledWith('tool_started', { tool_id: 'ftl-checker' }));
    expect(sdk.client.opt_in_capturing).not.toHaveBeenCalled();
    expect(sdk.client.opt_out_capturing).not.toHaveBeenCalled();
    expect(sdk.client.identify).not.toHaveBeenCalled();
    expect(sdk.client.set_config).not.toHaveBeenCalled();
    expect(options.before_send({
      event: 'tool_completed',
      properties: { token: 'phc_test', distinct_id: 'anon-1', tool_id: 'ftl-checker', status: 'success' },
    })?.properties).toMatchObject({ tool_id: 'ftl-checker', status: 'success', $process_person_profile: false });
  });

  it('switches to full persistence when the visitor accepts, and back to memory if they withdraw', async () => {
    window.localStorage.setItem('ph_phc_test_posthog', '{}');
    const { captureEvent, CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    captureEvent('tool_started', { tool_id: 'kde-checker' });
    expect((await initializedOptions()).persistence).toBe('memory');

    document.cookie = 're_cookie_consent=accepted; path=/';
    captureEvent('tool_completed', { tool_id: 'kde-checker', status: 'success' });
    expect(sdk.client.set_config).toHaveBeenLastCalledWith({ persistence: 'localStorage+cookie' });
    expect(sdk.client.capture).toHaveBeenLastCalledWith('tool_completed', { tool_id: 'kde-checker', status: 'success' });

    document.cookie = 're_cookie_consent=declined; path=/';
    captureEvent('tool_started', { tool_id: 'kde-checker' });
    expect(sdk.client.set_config).toHaveBeenLastCalledWith({ persistence: 'memory' });
    expect(window.localStorage.getItem('ph_phc_test_posthog')).toBeNull();
    expect(sdk.client.capture).toHaveBeenLastCalledWith('tool_started', { tool_id: 'kde-checker' });
    expect(sdk.client.identify).not.toHaveBeenCalled();
  });

  it('starts in full persistence when consent was already given', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { captureEvent } = await providerModule();
    captureEvent('tool_started', { tool_id: 'ftl-checker' });
    expect((await initializedOptions()).persistence).toBe('localStorage+cookie');
  });

  it.each([
    ['https://eu.i.posthog.com/', 'https://eu.i.posthog.com'],
    ['http://localhost:8000/', 'http://localhost:8000'],
    ['not-a-url', 'https://us.i.posthog.com'],
    ['ftp://eu.i.posthog.com', 'https://us.i.posthog.com'],
    ['https://user:secret@eu.i.posthog.com', 'https://us.i.posthog.com'], // pragma: allowlist secret
  ])('uses a valid API host or the safe fallback for %s', async (host, expectedHost) => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_HOST', host);
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);

    const options = await initializedOptions();
    expect(options).toMatchObject({
      api_host: expectedHost,
      autocapture: false,
      capture_pageview: false,
      disable_session_recording: true,
      persistence: 'localStorage+cookie',
    });
  });

  it('queues pre-init captures, sends them through posthog-js, and never uses sendBeacon', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { captureEvent } = await providerModule();
    captureEvent('tool_started', {
      tool_id: 'ftl-checker',
      email: 'lead@example.com',
      cta_label: '555-123-4567',
      source: 'Jane Sellers',
      path: '/pricing/Jane-Sellers',
    });
    captureEvent('tool_completed', { tool_id: 'ftl-checker', lead_captured: true });

    await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledTimes(2));
    expect(sdk.client.capture).toHaveBeenNthCalledWith(1, 'tool_started', { tool_id: 'ftl-checker' });
    expect(sdk.client.capture).toHaveBeenNthCalledWith(2, 'tool_completed', {
      tool_id: 'ftl-checker', lead_captured: true,
    });
    expect(sendBeacon).not.toHaveBeenCalled();
  });

  it('removes SDK-added PII from event properties and person updates before send', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    window.history.replaceState({}, '', '/tools/ftl-checker?email=lead%40example.com');
    const { CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    const { before_send: beforeSend } = await initializedOptions();

    const result = beforeSend({
      event: '$pageview',
      properties: {
        token: 'phc_test', distinct_id: 'anonymous-123',
        $pathname: '/tools/ftl-checker',
        $current_url: 'https://regengine.co/tools/ftl-checker?email=lead@example.com',
        $referrer: 'https://example.com/?email=lead@example.com',
        $host: 'lead@example.com:3000',
        $referring_domain: 'Example.com',
        $session_entry_url: 'https://regengine.co/?email=lead@example.com',
        $initial_referring_domain: 'example.com',
        utm_source: 'lead@example.com',
        utm_medium: '555-123-4567',
        utm_campaign: '1234567',
        $session_id: 'lead@example.com',
        $title: 'Report for lead@example.com',
        title: 'Report for lead@example.com',
        email: 'lead@example.com',
        tool_id: 'ftl-checker',
        $process_person_profile: false,
      },
      $set: { email: 'lead@example.com' },
      $set_once: { $initial_current_url: 'https://regengine.co/?email=lead@example.com' },
      $unset: ['email'],
    });

    expect(result).not.toBeNull();
    expect(result?.properties).toEqual({
      token: 'phc_test',
      distinct_id: 'anonymous-123',
      tool_id: 'ftl-checker',
      $process_person_profile: false,
      $referring_domain: '$direct',
      $pathname: '/tools/ftl-checker',
      $current_url: `${window.location.origin}/tools/ftl-checker`,
    });
    expect(result?.$set).toBeUndefined();
    expect(result?.$set_once).toBeUndefined();
    expect(result?.$unset).toBeUndefined();
    expect(JSON.stringify(result)).not.toContain('lead@example.com');
  });

  it('keeps validated SDK attribution and simple device properties', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    const { before_send: beforeSend } = await initializedOptions();

    const result = beforeSend({
      event: 'tool_started',
      properties: {
        token: 'phc_test', distinct_id: 'anonymous-123', tool_id: 'ftl-checker',
        $host: 'regengine.co', $referring_domain: 'linkedin.com',
        utm_source: 'linkedin.com', utm_medium: 'social', utm_campaign: 'fsma_launch',
        $session_id: 'abc-def', $window_id: 'abc-123', $lib: 'web',
        $lib_version: '1.2.3', $device_type: 'Desktop',
        $browser: 'Mobile Safari', $os: 'Mac OS X',
        $referrer: 'https://linkedin.com/?email=lead@example.com',
        $initial_utm_source: 'private', unknown: 'private',
      },
      $set: { email: 'lead@example.com' },
      $set_once: { email: 'lead@example.com' },
    });

    expect(result?.properties).toEqual({
      token: 'phc_test', distinct_id: 'anonymous-123', tool_id: 'ftl-checker',
      $process_person_profile: false,
      $host: 'regengine.co', $referring_domain: 'linkedin.com',
      utm_source: 'linkedin.com', utm_medium: 'social', utm_campaign: 'fsma_launch',
      $session_id: 'abc-def', $window_id: 'abc-123', $lib: 'web',
      $lib_version: '1.2.3', $device_type: 'Desktop',
      $browser: 'Mobile Safari', $os: 'Mac OS X',
    });
    expect(result?.$set).toBeUndefined();
    expect(result?.$set_once).toBeUndefined();
    expect(JSON.stringify(result)).not.toContain('lead@example.com');
  });

  it('keeps $direct and rejects malformed attribution values', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    const { before_send: beforeSend } = await initializedOptions();
    const base = { token: 'phc_test', distinct_id: 'anonymous-123' };

    expect(beforeSend({
      event: 'tool_started', properties: { ...base, $referring_domain: '$direct' },
    })?.properties.$referring_domain).toBe('$direct');

    for (const [key, value] of [
      ['$host', 'https://regengine.co'], ['$host', 'regengine.co:443'],
      ['$host', 'user@regengine.co'], ['$host', 'regengine.co/path'],
      ['$host', 'bad..example.com'],
      ['$referring_domain', 'LinkedIn.com'], ['$referring_domain', 'linkedin.com?email=lead@example.com'],
      ['$referring_domain', 'a'.repeat(254)], ['$referring_domain', 'bad-.example.com'],
      ['utm_source', 'lead@example.com'], ['utm_source', '1234567'],
      ['utm_source', '555-123-4567'], ['utm_source', 'https://linkedin.com'],
      ['utm_medium', 'paid.social'], ['utm_campaign', '5551234567'],
      ['$session_id', 'lead@example.com'], ['$window_id', '1234567'],
      ['$lib', 'https://example.com'], ['$lib_version', '555-123-4567'],
      ['$device_type', { email: 'lead@example.com' }],
      ['$browser', 'lead@example.com'], ['$os', 'Report for lead@example.com'],
    ] as const) {
      const result = beforeSend({ event: 'tool_started', properties: { ...base, [key]: value } });
      expect(result?.properties, `${key}=${String(value)}`).not.toHaveProperty(key);
    }
  });

  it('derives only safe landing attribution when the SDK does not supply it', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    window.history.replaceState({}, '', '/pricing?utm_source=linkedin.com&utm_medium=social&utm_campaign=fsma_launch&utm_content=lead%40example.com');
    Object.defineProperty(document, 'referrer', {
      configurable: true, value: 'https://news.example.com/article?email=lead@example.com',
    });
    const { CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    const { before_send: beforeSend } = await initializedOptions();
    const base = {
      event: '$pageview',
      properties: {
        token: 'phc_test', distinct_id: 'anonymous-123', $pathname: '/pricing',
        $current_url: window.location.href,
      },
    };

    const result = beforeSend(base);
    expect(result?.properties).toEqual({
      token: 'phc_test', distinct_id: 'anonymous-123', $process_person_profile: false,
      $referring_domain: 'news.example.com',
      utm_source: 'linkedin.com', utm_medium: 'social', utm_campaign: 'fsma_launch',
      $pathname: '/pricing', $current_url: 'https://regengine.co/pricing',
    });
    expect(JSON.stringify(result)).not.toContain('lead@example.com');

    window.history.replaceState({}, '', '/pricing?utm_source=lead%40example.com&utm_campaign=5551234567');
    const invalid = beforeSend(base);
    expect(invalid?.properties).not.toHaveProperty('utm_source');
    expect(invalid?.properties).not.toHaveProperty('utm_campaign');
  });

  it.each(['localhost', '127.0.0.1', 'dev.local', 'branch.vercel.app'])(
    'does not initialize or capture on %s', async (hostname) => {
      jsdom.reconfigure({ url: `https://${hostname}/tools/ftl-checker` });
      document.cookie = 're_cookie_consent=accepted; path=/';
      const { captureEvent, CSPostHogProvider } = await providerModule();
      render(<CSPostHogProvider>content</CSPostHogProvider>);
      captureEvent('tool_started', { tool_id: 'ftl-checker' });
      await vi.dynamicImportSettled();
      expect(sdk.imported).not.toHaveBeenCalled();
      expect(sdk.client.init).not.toHaveBeenCalled();
      expect(sdk.client.capture).not.toHaveBeenCalled();
    },
  );

  it('requires the exact true override on localhost', async () => {
    vi.stubEnv('NEXT_PUBLIC_POSTHOG_ALLOW_LOCALHOST', 'TRUE');
    jsdom.reconfigure({ url: 'http://localhost:3000/tools/ftl-checker' });
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { captureEvent, CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    captureEvent('tool_started', { tool_id: 'ftl-checker' });
    await vi.dynamicImportSettled();
    expect(sdk.client.init).not.toHaveBeenCalled();
    expect(sdk.client.capture).not.toHaveBeenCalled();
  });

  it('stops capture and beforeSend if an initialized client sees a preview hostname', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { captureEvent, CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    const { before_send: beforeSend } = await initializedOptions();
    sdk.client.capture.mockClear();
    jsdom.reconfigure({ url: 'https://branch.vercel.app/tools/ftl-checker' });

    captureEvent('tool_started', { tool_id: 'ftl-checker' });
    expect(sdk.client.capture).not.toHaveBeenCalled();
    expect(beforeSend({
      event: 'tool_started',
      properties: { token: 'phc_test', distinct_id: 'anonymous-123', tool_id: 'ftl-checker' },
    })).toBeNull();
  });

  it.each(['localhost', '127.0.0.1', 'dev.local', 'branch.vercel.app'])(
    'allows %s only with the exact localhost override', async (hostname) => {
      vi.stubEnv('NEXT_PUBLIC_POSTHOG_ALLOW_LOCALHOST', 'true');
      jsdom.reconfigure({ url: `https://${hostname}/tools/ftl-checker` });
      document.cookie = 're_cookie_consent=accepted; path=/';
      const { captureEvent, CSPostHogProvider } = await providerModule();
      render(<CSPostHogProvider>content</CSPostHogProvider>);
      captureEvent('tool_started', { tool_id: 'ftl-checker' });
      await initializedOptions();
      await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledWith('tool_started', {
        tool_id: 'ftl-checker',
      }));
    },
  );

  it('drops a capture if an older persisted distinct ID is an email address', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { CSPostHogProvider } = await providerModule();
    render(<CSPostHogProvider>content</CSPostHogProvider>);
    const { before_send: beforeSend } = await initializedOptions();

    expect(beforeSend({
      event: 'tool_started',
      properties: { token: 'phc_test', distinct_id: 'lead@example.com', tool_id: 'ftl-checker' },
    })).toBeNull();
  });
});

describe('PostHog App Router pageviews', () => {
  it('captures the initial public route and each public route change after consent', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    const { CSPostHogProvider } = await providerModule();
    const { rerender } = render(<CSPostHogProvider>content</CSPostHogProvider>);
    await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledWith('$pageview', {
      $pathname: '/tools/ftl-checker',
    }));
    sdk.client.capture.mockClear();

    navigation.pathname = '/pricing';
    window.history.replaceState({}, '', '/pricing?utm_source=newsletter');
    navigation.search = 'utm_source=newsletter';
    rerender(<CSPostHogProvider>content</CSPostHogProvider>);
    await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledWith('$pageview', {
      $pathname: '/pricing',
    }));
    expect(JSON.stringify(sdk.client.capture.mock.calls)).not.toContain('utm_source');

    sdk.client.capture.mockClear();
    navigation.pathname = '/pricing/Jane-Sellers';
    window.history.replaceState({}, '', '/pricing/Jane-Sellers');
    navigation.search = '';
    rerender(<CSPostHogProvider>content</CSPostHogProvider>);
    await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledWith('$pageview', {
      $pathname: '/pricing',
    }));
    expect(JSON.stringify(sdk.client.capture.mock.calls)).not.toContain('Jane-Sellers');
  });

  it('skips app routes and internal sessions, then resumes after re_internal=0', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    navigation.pathname = '/dashboard';
    window.history.replaceState({}, '', '/dashboard');
    const { CSPostHogProvider } = await providerModule();
    const { rerender } = render(<CSPostHogProvider>content</CSPostHogProvider>);
    await initializedOptions();
    expect(sdk.client.capture).not.toHaveBeenCalled();

    navigation.pathname = '/pricing';
    navigation.search = 're_internal=1';
    window.history.replaceState({}, '', '/pricing?re_internal=1');
    rerender(<CSPostHogProvider>content</CSPostHogProvider>);
    expect(window.localStorage.getItem('re_internal')).toBe('1');
    expect(sdk.client.capture).not.toHaveBeenCalled();

    navigation.search = 're_internal=0';
    window.history.replaceState({}, '', '/pricing?re_internal=0');
    rerender(<CSPostHogProvider>content</CSPostHogProvider>);
    await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledWith('$pageview', {
      $pathname: '/pricing',
    }));
    expect(window.localStorage.getItem('re_internal')).toBeNull();
  });

  it('opts the SDK in before capturing when an internal session is cleared', async () => {
    document.cookie = 're_cookie_consent=accepted; path=/';
    navigation.pathname = '/dashboard';
    window.history.replaceState({}, '', '/dashboard');
    const { CSPostHogProvider } = await providerModule();
    const { rerender } = render(<CSPostHogProvider>content</CSPostHogProvider>);
    await initializedOptions();

    navigation.pathname = '/pricing';
    navigation.search = 're_internal=1';
    window.history.replaceState({}, '', '/pricing?re_internal=1');
    rerender(<CSPostHogProvider>content</CSPostHogProvider>);
    expect(window.localStorage.getItem('re_internal')).toBe('1');

    // The provider's poll can opt out between these two route changes.
    sdk.client.has_opted_out_capturing.mockReturnValue(true);
    sdk.client.opt_in_capturing.mockClear();
    sdk.client.capture.mockClear();
    navigation.search = 're_internal=0';
    window.history.replaceState({}, '', '/pricing?re_internal=0');
    rerender(<CSPostHogProvider>content</CSPostHogProvider>);

    await waitFor(() => expect(sdk.client.capture).toHaveBeenCalledWith('$pageview', {
      $pathname: '/pricing',
    }));
    expect(sdk.client.opt_in_capturing).toHaveBeenCalledTimes(1);
    expect(sdk.client.opt_in_capturing.mock.invocationCallOrder[0])
      .toBeLessThan(sdk.client.capture.mock.invocationCallOrder[0]);
  });
});
