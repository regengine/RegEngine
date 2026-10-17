'use client';

import { Suspense, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import type posthog from 'posthog-js';
import type { CaptureResult } from 'posthog-js';
import { getStoredConsent } from './cookie-consent';
import {
  isInternalAnalyticsSession,
  safeMarketingPath,
  shouldTrackMarketingPageview,
} from './marketing-analytics-routes';

type CTAClickProps = { cta_label: string; page: string; destination?: string };
type SignupStartProps = { plan?: string; source?: string };
type OnboardingCompleteProps = { step: string; tenant_id?: string };
type ToolVisitProps = { tool: string; path: string };
type Capture = { event: string; properties: Record<string, unknown> };

const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const DEFAULT_POSTHOG_HOST = 'https://us.i.posthog.com';
const SAFE_PROPERTY_KEYS = new Set([
  'tool_id', 'lead_captured', 'categories_selected', 'covered_count',
  'risk_level', 'status', 'total_events', 'non_compliant_events',
  'compliant_events',
]);
const SAFE_LABEL = /^[a-z0-9][a-z0-9_-]{0,79}$/i;
const SAFE_SOURCE_LABEL = /^[a-z0-9][a-z0-9_.-]{0,79}$/i;
const SAFE_SDK_STRING = /^[a-z0-9](?:[a-z0-9_. -]{0,78}[a-z0-9])?$/i;
const HOST_LABEL = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/i;
const SDK_SIMPLE_KEYS = [
  '$session_id', '$window_id', '$lib', '$lib_version', '$device_type', '$browser', '$os',
] as const;
const PHONE_SHAPE = /\d{3}[-_. ]\d{3}[-_. ]\d{4}/;
const pendingCaptures: Capture[] = [];
let client: typeof posthog | null = null;
let initPromise: Promise<void> | null = null;

function hasConsent(): boolean {
  return getStoredConsent() === 'accepted';
}

function isAllowedAnalyticsHost(): boolean {
  if (typeof window === 'undefined') return false;
  if (process.env.NEXT_PUBLIC_POSTHOG_ALLOW_LOCALHOST === 'true') return true;
  const hostname = window.location.hostname.toLowerCase();
  return hostname !== 'localhost' && hostname !== '127.0.0.1'
    && !hostname.endsWith('.local') && !hostname.endsWith('.vercel.app');
}

function configuredKey(): string | null {
  return posthogKey && posthogKey !== 'phc_placeholder' ? posthogKey : null;
}

function apiHost(): string {
  const configured = process.env.NEXT_PUBLIC_POSTHOG_HOST;
  if (!configured) return DEFAULT_POSTHOG_HOST;
  try {
    const url = new URL(configured);
    if ((url.protocol === 'https:' || url.protocol === 'http:') && !url.username && !url.password) {
      return configured.replace(/\/$/, '');
    }
  } catch {
    // A non-URL host setting must not create a broken capture endpoint.
  }
  return DEFAULT_POSTHOG_HOST;
}

function isSafeString(value: unknown, pattern: RegExp = SAFE_LABEL): value is string {
  return typeof value === 'string' && pattern.test(value)
    && !/\d{7,}/.test(value) && !PHONE_SHAPE.test(value);
}

function safeHostname(value: unknown, lowercaseOnly: boolean): string | undefined {
  if (typeof value !== 'string' || value.length === 0 || value.length > 253
    || (lowercaseOnly && value !== value.toLowerCase())
    || /\d{7,}/.test(value) || PHONE_SHAPE.test(value)) return undefined;
  return value.split('.').every((label) => label.length <= 63 && HOST_LABEL.test(label))
    ? value : undefined;
}

function safeValue(value: unknown): string | number | boolean | string[] | undefined {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (isSafeString(value)) return value;
  if (Array.isArray(value) && value.length <= 20) {
    const strings = value.map(safeValue);
    if (strings.every((item): item is string => typeof item === 'string')) return strings;
  }
  return undefined;
}

function safeProperties(properties: Record<string, unknown> = {}): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(properties)) {
    if (!SAFE_PROPERTY_KEYS.has(key)) continue;
    const cleaned = safeValue(value);
    if (cleaned !== undefined) result[key] = cleaned;
  }
  return result;
}

/** PostHog adds URL, referrer, title, and campaign data; only approved fields leave this callback. */
function beforeSend(capture: CaptureResult | null): CaptureResult | null {
  if (!capture || !hasConsent() || !isAllowedAnalyticsHost() || isInternalAnalyticsSession()) return null;
  if (capture.event.startsWith('$') && capture.event !== '$pageview') return null;
  const token = capture.properties.token;
  const distinctId = capture.properties.distinct_id;
  if (typeof token !== 'string' || typeof distinctId !== 'string' || !SAFE_LABEL.test(distinctId)) return null;
  const properties = safeProperties(capture.properties) as CaptureResult['properties'];
  properties.token = token;
  properties.distinct_id = distinctId;
  properties.$process_person_profile = false;

  const host = safeHostname(capture.properties.$host, false);
  if (host) properties.$host = host;
  const referringDomain = capture.properties.$referring_domain;
  if (referringDomain === '$direct') properties.$referring_domain = '$direct';
  else {
    const domain = safeHostname(referringDomain, true);
    if (domain) properties.$referring_domain = domain;
  }
  for (const key of ['utm_source', 'utm_medium', 'utm_campaign'] as const) {
    const value = capture.properties[key];
    if (isSafeString(value, key === 'utm_source' ? SAFE_SOURCE_LABEL : SAFE_LABEL)) {
      properties[key] = value;
    }
  }
  // SDK campaign/referrer persistence is disabled; derive only safe pageview attribution.
  if (capture.event === '$pageview') {
    const params = new URLSearchParams(window.location.search);
    for (const key of ['utm_source', 'utm_medium', 'utm_campaign'] as const) {
      const value = params.get(key);
      if (properties[key] === undefined
        && isSafeString(value, key === 'utm_source' ? SAFE_SOURCE_LABEL : SAFE_LABEL)) {
        properties[key] = value;
      }
    }
    if (properties.$referring_domain === undefined) {
      if (!document.referrer) properties.$referring_domain = '$direct';
      else {
        try {
          const domain = safeHostname(new URL(document.referrer).hostname.toLowerCase(), true);
          if (domain) properties.$referring_domain = domain;
        } catch {
          // Invalid referrers must not be sent.
        }
      }
    }
  }
  for (const key of SDK_SIMPLE_KEYS) {
    const value = capture.properties[key];
    if (isSafeString(value, SAFE_SDK_STRING)) properties[key] = value;
  }

  if (capture.event === '$pageview') {
    const pathname = safeMarketingPath(capture.properties.$pathname);
    if (!pathname || !shouldTrackMarketingPageview(pathname)) return null;
    properties.$pathname = pathname;
    properties.$current_url = `${window.location.origin}${pathname}`;
  }

  return { ...capture, properties, $set: undefined, $set_once: undefined, $unset: undefined };
}

async function initializePostHog(): Promise<void> {
  const key = configuredKey();
  if (!key || !hasConsent() || !isAllowedAnalyticsHost() || isInternalAnalyticsSession() || client) return;
  if (initPromise) return initPromise;
  initPromise = import('posthog-js').then(({ default: posthogClient }) => {
    if (!hasConsent() || !isAllowedAnalyticsHost() || isInternalAnalyticsSession()) {
      pendingCaptures.length = 0;
      return;
    }
    posthogClient.init(key, {
      api_host: apiHost(),
      autocapture: false,
      capture_pageview: false,
      disable_session_recording: true,
      persistence: 'localStorage+cookie',
      save_campaign_params: false,
      save_referrer: false,
      advanced_disable_flags: true,
      disable_surveys: true,
      person_profiles: 'never',
      before_send: beforeSend,
    });
    if (posthogClient.has_opted_out_capturing()) posthogClient.opt_in_capturing();
    client = posthogClient;
    for (const { event, properties } of pendingCaptures.splice(0)) {
      if (!hasConsent() || !isAllowedAnalyticsHost() || isInternalAnalyticsSession()) break;
      client.capture(event, properties);
    }
  }).catch(() => {
    pendingCaptures.length = 0;
  }).finally(() => {
    initPromise = null;
  });
  return initPromise;
}

export function captureEvent(event: string, properties?: Record<string, unknown>): void {
  if (!configuredKey() || !hasConsent() || !isAllowedAnalyticsHost() || isInternalAnalyticsSession()) return;
  if (!/^[a-z0-9_$-]+$/i.test(event) || (event.startsWith('$') && event !== '$pageview')) return;
  const capture: Capture = { event, properties: safeProperties(properties) };
  if (event === '$pageview') {
    const pathname = safeMarketingPath(properties?.$pathname);
    if (!pathname || !shouldTrackMarketingPageview(pathname)) return;
    capture.properties.$pathname = pathname;
  }
  if (client) {
    if (client.has_opted_out_capturing()) client.opt_in_capturing();
    client.capture(capture.event, capture.properties);
  } else {
    pendingCaptures.push(capture);
    void initializePostHog();
  }
}

const posthogClient = { capture: captureEvent };

export function usePostHog() {
  return posthogClient;
}

export const ph = {
  ctaClick: (props: CTAClickProps) => captureEvent('cta_clicked', props),
  signupStart: (props: SignupStartProps) => captureEvent('signup_started', props),
  onboardingComplete: (props: OnboardingCompleteProps) => captureEvent('onboarding_completed', props),
  toolVisit: (props: ToolVisitProps) => captureEvent('tool_visited', props),
};

function PostHogPageviewTracker({ consentGranted }: { consentGranted: boolean }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (consentGranted && shouldTrackMarketingPageview(pathname, window.location.href)) {
      captureEvent('$pageview', { $pathname: pathname });
    }
  }, [consentGranted, pathname, searchParams]);

  return null;
}

export function CSPostHogProvider({ children }: { children: ReactNode }) {
  const [consentGranted, setConsentGranted] = useState(false);

  useEffect(() => {
    const refresh = () => {
      const accepted = hasConsent();
      setConsentGranted(accepted);
      if (accepted && isAllowedAnalyticsHost() && !isInternalAnalyticsSession()) {
        if (client?.has_opted_out_capturing()) client.opt_in_capturing();
        void initializePostHog();
      } else {
        pendingCaptures.length = 0;
        if (client && !client.has_opted_out_capturing()) client.opt_out_capturing();
      }
    };
    refresh();
    const interval = window.setInterval(refresh, 1000);
    return () => window.clearInterval(interval);
  }, []);

  return <>
    {children}
    <Suspense fallback={null}>
      <PostHogPageviewTracker consentGranted={consentGranted} />
    </Suspense>
  </>;
}
