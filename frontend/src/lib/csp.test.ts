import { describe, expect, it } from 'vitest';

import {
  buildCsp,
  CSP_PROXY_MATCHER,
  shouldApplyCspProxy,
} from './csp';
import { config as proxyConfig } from '@/proxy';

function parseDirectives(policy: string): Record<string, string[]> {
  return Object.fromEntries(
    policy
      .split(';')
      .map((directive) => directive.trim())
      .filter(Boolean)
      .map((directive) => {
        const [name, ...values] = directive.split(/\s+/);
        return [name, values];
      }),
  );
}

describe('buildCsp', () => {
  it('builds an enforced nonce-based script policy without unsafe script fallbacks', () => {
    const directives = parseDirectives(buildCsp('test-nonce'));

    expect(directives['script-src']).toEqual(
      expect.arrayContaining(["'self'", "'nonce-test-nonce'", "'strict-dynamic'"]),
    );
    expect(directives['script-src']).not.toContain("'unsafe-inline'");
    expect(directives['script-src']).not.toContain("'unsafe-eval'");
  });

  it('allows required first-party integrations without weakening framing or object policy', () => {
    const directives = parseDirectives(buildCsp('test-nonce'));

    expect(directives['style-src']).toEqual(
      expect.arrayContaining(["'self'", "'unsafe-inline'", 'https://fonts.googleapis.com']),
    );
    expect(directives['font-src']).toEqual(
      expect.arrayContaining(["'self'", 'https://fonts.gstatic.com']),
    );
    expect(directives['connect-src']).toEqual(
      expect.arrayContaining([
        "'self'",
        'https://*.supabase.co',
        'wss://*.supabase.co',
        'https://*.railway.app',
        'https://*.vercel.app',
        'https://*.sentry.io',
        'https://app.posthog.com',
        'https://*.posthog.com',
      ]),
    );
    expect(directives['frame-src']).toEqual(["'none'"]);
    expect(directives['frame-ancestors']).toEqual(["'none'"]);
    expect(directives['object-src']).toEqual(["'none'"]);
    expect(directives['base-uri']).toEqual(["'self'"]);
    expect(directives['form-action']).toEqual(["'self'"]);
    expect(directives['upgrade-insecure-requests']).toEqual([]);
  });
});

describe('CSP proxy matcher', () => {
  it('is wired into the Next proxy config', () => {
    expect(CSP_PROXY_MATCHER).toBe('/((?!_next/static|_next/image|favicon.ico).*)');
    expect(proxyConfig.matcher).toEqual([CSP_PROXY_MATCHER]);
  });

  it('covers public pages, app pages, and API routes by default', () => {
    expect(shouldApplyCspProxy('/')).toBe(true);
    expect(shouldApplyCspProxy('/pricing')).toBe(true);
    expect(shouldApplyCspProxy('/tools/ftl-checker')).toBe(true);
    expect(shouldApplyCspProxy('/login')).toBe(true);
    expect(shouldApplyCspProxy('/dashboard')).toBe(true);
    expect(shouldApplyCspProxy('/api/health')).toBe(true);
  });

  it('leaves Next internals and favicon outside the proxy', () => {
    expect(shouldApplyCspProxy('/_next/static/chunks/app.js')).toBe(false);
    expect(shouldApplyCspProxy('/_next/image')).toBe(false);
    expect(shouldApplyCspProxy('/favicon.ico')).toBe(false);
  });
});
