'use client';

import { Suspense, useEffect } from 'react';
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
type SignupProps = { source?: string };
type Capture = { event: string; properties: Record<string, unknown> };

const posthogKey = process.env.NEXT_PUBLIC_POSTHOG_KEY;
const DEFAULT_POSTHOG_HOST = 'https://us.i.posthog.com';
const SAFE_PROPERTY_KEYS = new Set([
  'tool_id', 'lead_captured', 'categories_selected', 'covered_count',
  'risk_level', 'status', 'total_events', 'non_compliant_events',
  'compliant_events', 'tool', 'outcome', 'error_code', 'placement', 'form', 'step',
  'grade', 'webinar',
]);
const EMAIL_SHAPE = /^[^\s@]{1,64}@[^\s@]{1,253}\.[^\s@]{2,63}$/;
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
let clientMode: TrackingMode | null = null;
/** Pending or applied email; never sent until consent (C.Lee #3645 on A-2138/A-2139). */
let identifiedEmail: string | null = null;
let identifyApplied = false;

/**
 * Cookieless until consent (C.Lee, A-2138, Oct 27 2026): before Accept the SDK keeps its
 * anonymous ID in memory only, so it writes no cookie or storage and nothing outlives the tab.
 * After Accept it switches to normal persistence. Identify-by-email is consent-gated on top
 * of that (C.Lee, #3645): pre-consent never identifies; post-consent may identify and switch
 * person_profiles to identified_only; decline/revoke resets and returns to never/cookieless.
 * Decline stops all capture, cookieless included (C.Lee, A-2139). The choice lives in the
 * re_cookie_consent cookie, so it holds on later page loads.
 */
type TrackingMode = 'full' | 'cookieless';
const FULL_PERSISTENCE = 'localStorage+cookie' as const;
const COOKIELESS_PERSISTENCE = 'memory' as const;

function normalizeEmail(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const email = value.trim().toLowerCase();
  return email.length <= 254 && EMAIL_SHAPE.test(email) ? email : null;
}

function hasConsent(): boolean {
  return getStoredConsent() === 'accepted';
}

function hasDeclined(): boolean {
  return getStoredConsent() === 'declined';
}

function trackingMode(): TrackingMode {
  return hasConsent() ? 'full' : 'cookieless';
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

function canTrack(): boolean {
  return configuredKey() !== null && !hasDeclined()
    && isAllowedAnalyticsHost() && !isInternalAnalyticsSession();
}

/** Remove what full tracking stored, for a visitor who declines after accepting. */
function clearStoredIdentity(): void {
  const key = configuredKey();
  if (!key || typeof document === 'undefined') return;
  const name = `ph_${key}_posthog`;
  const hostname = window.location.hostname;
  const parts = hostname.split('.');
  const domains = ['', `; domain=${hostname}`];
  if (parts.length > 1) domains.push(`; domain=.${parts.slice(-2).join('.')}`);
  for (const domain of domains) document.cookie = `${name}=; max-age=0; path=/${domain}`;
  try {
    window.localStorage.removeItem(name);
  } catch {
    // Storage can be unavailable; there is nothing to clear then.
  }
}

/** Keep the SDK's persistence in step with the visitor's current consent. */
function applyTrackingMode(): void {
  if (!client) return;
  const mode = trackingMode();
  if (mode === clientMode) return;
  client.set_config({ persistence: mode === 'full' ? FULL_PERSISTENCE : COOKIELESS_PERSISTENCE });
  if (mode === 'full' && client.has_opted_out_capturing()) client.opt_in_capturing();
  clientMode = mode;
}

/**
 * Apply a pending email identify only after Accept. Switches person_profiles to
 * identified_only for that person; pre-consent stays person_profiles never.
 */
function applyIdentify(): void {
  if (!client || !identifiedEmail || identifyApplied || !hasConsent()) return;
  identifyApplied = true;
  client.set_config({ person_profiles: 'identified_only' });
  client.identify(identifiedEmail, { email: identifiedEmail });
}

function clearIdentifyState(options: { resetClient: boolean }): void {
  const hadAppliedIdentify = identifyApplied;
  identifiedEmail = null;
  identifyApplied = false;
  if (!client) return;
  if (options.resetClient && hadAppliedIdentify) client.reset();
  client.set_config({ person_profiles: 'never' });
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
  if (!capture || hasDeclined() || !isAllowedAnalyticsHost() || isInternalAnalyticsSession()) return null;
  const isIdentify = capture.event === '$identify';
  // $identify is allowed only after consent with a matching identified email; no other $ events.
  if (capture.event.startsWith('$') && capture.event !== '$pageview' && !isIdentify) return null;
  if (isIdentify && !hasConsent()) return null;
  const token = capture.properties.token;
  const distinctId = capture.properties.distinct_id;
  const isIdentified = hasConsent()
    && identifiedEmail !== null
    && distinctId === identifiedEmail;
  if (typeof token !== 'string' || typeof distinctId !== 'string'
    || (!SAFE_LABEL.test(distinctId) && !isIdentified)) return null;
  if (isIdentify && !isIdentified) return null;
  const properties = safeProperties(capture.properties) as CaptureResult['properties'];
  properties.token = token;
  properties.distinct_id = distinctId;
  if (isIdentify) {
    const anonId = capture.properties.$anon_distinct_id;
    if (typeof anonId === 'string' && SAFE_LABEL.test(anonId)) properties.$anon_distinct_id = anonId;
    // Only the email reaches the person profile; no other $set keys are sent.
    return {
      ...capture,
      properties,
      $set: { email: identifiedEmail },
      $set_once: undefined,
      $unset: undefined,
    };
  }
  // Anonymous / pre-identify events never create or enrich a person profile.
  if (!isIdentified) properties.$process_person_profile = false;

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
  if (!key || !canTrack() || client) return;
  if (initPromise) return initPromise;
  initPromise = import('posthog-js').then(({ default: posthogClient }) => {
    if (!canTrack()) {
      pendingCaptures.length = 0;
      return;
    }
    const mode = trackingMode();
    posthogClient.init(key, {
      api_host: apiHost(),
      autocapture: false,
      capture_pageview: false,
      disable_session_recording: true,
      persistence: mode === 'full' ? FULL_PERSISTENCE : COOKIELESS_PERSISTENCE,
      save_campaign_params: false,
      save_referrer: false,
      advanced_disable_flags: true,
      disable_surveys: true,
      // Stay never until a consented identify; applyIdentify upgrades to identified_only.
      person_profiles: 'never',
      before_send: beforeSend,
    });
    // Opting in writes a consent record, so only do it once the visitor has accepted.
    if (mode === 'full' && posthogClient.has_opted_out_capturing()) posthogClient.opt_in_capturing();
    client = posthogClient;
    clientMode = mode;
    applyIdentify();
    for (const { event, properties } of pendingCaptures.splice(0)) {
      if (!canTrack()) break;
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
  if (!canTrack()) return;
  if (!/^[a-z0-9_$-]+$/i.test(event) || (event.startsWith('$') && event !== '$pageview')) return;
  const capture: Capture = { event, properties: safeProperties(properties) };
  if (event === '$pageview') {
    const pathname = safeMarketingPath(properties?.$pathname);
    if (!pathname || !shouldTrackMarketingPageview(pathname)) return;
    capture.properties.$pathname = pathname;
  }
  if (client) {
    applyTrackingMode();
    if (clientMode === 'full' && client.has_opted_out_capturing()) client.opt_in_capturing();
    client.capture(capture.event, capture.properties);
  } else {
    pendingCaptures.push(capture);
    void initializePostHog();
  }
}

/**
 * Stores the visitor's email and, only after Accept, ties events to that person.
 * Pre-consent: email stays in-memory in this tab and never leaves the browser.
 * Post-consent: identifies and switches person_profiles to identified_only.
 * Login-before-consent is a no-op for the network; identify fires when consent arrives.
 */
export function identifyUser(email: unknown): void {
  const normalized = normalizeEmail(email);
  if (!normalized) return;
  if (normalized !== identifiedEmail) {
    identifiedEmail = normalized;
    identifyApplied = false;
  }
  if (!hasConsent() || !canTrack()) return;
  if (client) {
    applyTrackingMode();
    applyIdentify();
  } else {
    void initializePostHog();
  }
}

/** Clears the identified email on sign-out so later events are anonymous again. */
export function resetAnalyticsIdentity(): void {
  clearIdentifyState({ resetClient: true });
}

const posthogClient = { capture: captureEvent, identify: identifyUser };

export function usePostHog() {
  return posthogClient;
}

export const ph = {
  ctaClick: (props: CTAClickProps) => captureEvent('cta_clicked', props),
  signupStart: (props: SignupStartProps) => captureEvent('signup_started', props),
  onboardingComplete: (props: OnboardingCompleteProps) => captureEvent('onboarding_completed', props),
  toolVisit: (props: ToolVisitProps) => captureEvent('tool_visited', props),
  signup: (props: SignupProps) => captureEvent('signup', props),
};

function PostHogPageviewTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (shouldTrackMarketingPageview(pathname, window.location.href)) {
      captureEvent('$pageview', { $pathname: pathname });
    }
  }, [pathname, searchParams]);

  return null;
}

export function CSPostHogProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    const refresh = () => {
      if (canTrack()) {
        applyTrackingMode();
        void initializePostHog();
        // Consent may have arrived after a login-time identifyUser; apply now.
        applyIdentify();
      } else {
        pendingCaptures.length = 0;
        if (client && !client.has_opted_out_capturing()) client.opt_out_capturing();
        if (hasDeclined()) {
          clearIdentifyState({ resetClient: true });
          clearStoredIdentity();
          if (client) {
            client.set_config({ persistence: COOKIELESS_PERSISTENCE });
          }
          // Re-accepting later goes through applyTrackingMode, which opts back in.
          clientMode = null;
        }
      }
    };
    refresh();
    const interval = window.setInterval(refresh, 1000);
    return () => window.clearInterval(interval);
  }, []);

  return <>
    {children}
    <Suspense fallback={null}>
      <PostHogPageviewTracker />
    </Suspense>
  </>;
}
