'use client';

import { track } from '@vercel/analytics';
import { getStoredConsent } from '@/lib/cookie-consent';
import { captureEvent } from '@/lib/posthog-provider';

type Outcome = 'success' | 'error';
type ErrorCode = 'validation' | 'rate_limited' | 'unavailable' | 'server';
type Form = 'email_gate' | 'lead_gate';
type Step = 'verify' | 'confirm' | 'gate' | 'enrich';

type ConversionEvent =
  | 'tool_run_started'
  | 'tool_run_completed'
  | 'email_capture_submit'
  | 'waitlist_submit'
  | 'readiness_assessment_submit'
  | 'book_call_click'
  | 'contact_form_submit'
  | 'webinar_register_click';

type EventValue = string | number | boolean;
type Attribution = Partial<Record<'utm_source' | 'utm_medium' | 'utm_campaign', string>>;

const EVENT_NAMES = new Set<ConversionEvent>([
  'tool_run_started',
  'tool_run_completed',
  'email_capture_submit',
  'waitlist_submit',
  'readiness_assessment_submit',
  'book_call_click',
  'contact_form_submit',
  'webinar_register_click',
]);
const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign'] as const;
const EVENT_EXTRA_KEYS: Record<ConversionEvent, readonly string[]> = {
  tool_run_started: ['tool'],
  tool_run_completed: ['tool', 'outcome'],
  email_capture_submit: ['form', 'step', 'tool', 'outcome', 'error_code'],
  waitlist_submit: ['outcome', 'error_code'],
  readiness_assessment_submit: ['outcome', 'error_code', 'grade'],
  book_call_click: ['placement', 'tool'],
  contact_form_submit: ['outcome', 'error_code'],
  webinar_register_click: ['webinar', 'placement'],
};
const ENUM_VALUES: Record<string, readonly string[]> = {
  form: ['email_gate', 'lead_gate'],
  step: ['verify', 'confirm', 'gate', 'enrich'],
  outcome: ['success', 'error'],
  error_code: ['validation', 'rate_limited', 'unavailable', 'server'],
};
const CODE_VALUE = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;
const GRADE_VALUE = /^[A-F]$/;
const UTM_VALUE = /^[a-z0-9][a-z0-9._-]*$/;
const PHONE_SHAPE = /\d{3}[-_.]\d{3}[-_.]\d{4}/;
const UTM_STORAGE_KEY = 're_utm';
const INTERNAL_STORAGE_KEY = 're_internal';

/** Authenticated app routes are excluded from marketing Web Analytics. */
export const MARKETING_APP_ROUTE_PREFIXES = [
  '/dashboard', '/login', '/ingest', '/admin', '/audit', '/compliance',
  '/controls', '/developer/portal', '/exceptions', '/identity', '/incidents', '/onboarding',
  '/records', '/remediation', '/requests', '/reports', '/review', '/rules',
  '/settings', '/sysadmin', '/trace',
] as const;

let analyticsMounted = false;

/** Called by CookieBanner when consented Vercel Analytics mounts or unmounts. */
export function setConversionAnalyticsEnabled(enabled: boolean): void {
  analyticsMounted = enabled;
}

function cleanString(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const cleaned = value.trim().slice(0, 100);
  return cleaned || undefined;
}

function cleanPath(path: string): string | undefined {
  // Marketing routes are static; omit paths that look like an email or URL.
  if (/@|%40|:\/\/|%3a%2f%2f/i.test(path)) return undefined;
  return cleanString(path);
}

function cleanLeadUtm(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const cleaned = value.trim().toLowerCase();
  if (!cleaned || cleaned.includes('@') || cleaned.includes('://')) return undefined;
  return cleaned.slice(0, 100);
}

function cleanEventUtm(value: string | undefined): string | undefined {
  // Event properties must not expose free text or obvious phone numbers from URL tags.
  if (!value || !UTM_VALUE.test(value) || /\d{7,}/.test(value) || PHONE_SHAPE.test(value)) return undefined;
  return value;
}

function storedAttribution(): Attribution {
  try {
    const parsed: unknown = JSON.parse(sessionStorage.getItem(UTM_STORAGE_KEY) ?? '{}');
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const stored = parsed as Record<string, unknown>;
    const result: Attribution = {};
    for (const key of UTM_KEYS) {
      const value = cleanLeadUtm(stored[key]);
      if (value) result[key] = value;
    }
    return result;
  } catch {
    return {};
  }
}

/** Current URL values win; the first value of each UTM key is kept for session fallback. */
export function getConversionAttribution(): Attribution {
  if (typeof window === 'undefined') return {};
  const stored = storedAttribution();
  const current: Attribution = {};
  for (const key of UTM_KEYS) {
    const value = cleanLeadUtm(new URLSearchParams(window.location.search).get(key));
    if (value) {
      current[key] = value;
      if (!stored[key]) stored[key] = value;
    }
  }
  try {
    if (Object.keys(stored).length) sessionStorage.setItem(UTM_STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // Storage can be disabled; current URL attribution still works.
  }
  return { ...stored, ...current };
}

/** Only the hostname is returned; no referrer path or query reaches a lead row. */
export function getReferrerHostname(): string {
  if (typeof document === 'undefined' || !document.referrer) return '';
  try {
    return new URL(document.referrer).hostname.toLowerCase().slice(0, 100);
  } catch {
    return '';
  }
}

function internalDirective(url: string): string | null {
  try {
    return new URL(url, window.location.origin).searchParams.get(INTERNAL_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** Visiting ?re_internal=1 suppresses this browser; ?re_internal=0 clears it. */
export function isInternalAnalyticsSession(url?: string): boolean {
  if (typeof window === 'undefined') return false;
  const directive = internalDirective(url ?? window.location.href);
  try {
    if (directive === '1') window.localStorage.setItem(INTERNAL_STORAGE_KEY, '1');
    if (directive === '0') window.localStorage.removeItem(INTERNAL_STORAGE_KEY);
    return directive === '1' || (directive !== '0' && window.localStorage.getItem(INTERNAL_STORAGE_KEY) === '1');
  } catch {
    return directive === '1';
  }
}

function isAppRoute(path: string): boolean {
  return MARKETING_APP_ROUTE_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
}

/** Vercel Analytics beforeSend filter for app routes and tagged internal browsers. */
export function filterConversionAnalyticsEvent<T extends { url: string }>(event: T): T | null {
  if (isInternalAnalyticsSession() || isInternalAnalyticsSession(event.url)) return null;
  try {
    if (isAppRoute(new URL(event.url, window.location.origin).pathname)) return null;
  } catch {
    if (typeof window !== 'undefined' && isAppRoute(window.location.pathname)) return null;
  }
  return event;
}

function cleanExtra(key: string, value: unknown): EventValue | undefined {
  const cleaned = cleanString(value);
  if (!cleaned) return undefined;
  if (ENUM_VALUES[key]) return ENUM_VALUES[key].includes(cleaned) ? cleaned : undefined;
  if (key === 'grade') return GRADE_VALUE.test(cleaned) ? cleaned : undefined;
  if (key === 'tool' || key === 'placement' || key === 'webinar') {
    return CODE_VALUE.test(cleaned) ? cleaned : undefined;
  }
  // The current allowlisted extras all represent fixed labels, not numeric data.
  return undefined;
}

/** The only path to track(): caller-supplied keys cannot add PII or override attribution. */
export function trackConversionEvent(event: ConversionEvent, props: Record<string, unknown> = {}): void {
  if (!EVENT_NAMES.has(event) || typeof window === 'undefined') return;
  if (getStoredConsent() !== 'accepted' || isInternalAnalyticsSession()) return;
  if (isAppRoute(window.location.pathname)) return;

  const properties: Record<string, EventValue> = {};
  const path = cleanPath(window.location.pathname);
  if (path) properties.path = path;
  const attribution = getConversionAttribution();
  for (const key of UTM_KEYS) {
    const value = cleanEventUtm(attribution[key]);
    if (value) properties[key] = value;
  }
  for (const [key, value] of Object.entries(props)) {
    if (!EVENT_EXTRA_KEYS[event].includes(key)) continue;
    const cleaned = cleanExtra(key, value);
    if (cleaned !== undefined) properties[key] = cleaned;
  }
  if (properties.outcome !== 'error') delete properties.error_code;
  if (event === 'email_capture_submit' && properties.error_code === 'unavailable') delete properties.error_code;
  try {
    // PostHog has its own consent, host and property allowlist gates.
    captureEvent(event, properties);
  } catch {
    // Telemetry must not change the outcome of the user's tool or form action.
  }
  if (!analyticsMounted) return;
  try {
    track(event, properties);
  } catch {
    // Telemetry must not change the outcome of the user's tool or form action.
  }
}

export function trackToolRunStarted(tool: string): void {
  trackConversionEvent('tool_run_started', { tool });
}

export function trackToolRunCompleted(tool: string, outcome: Outcome): void {
  trackConversionEvent('tool_run_completed', { tool, outcome });
}

export function trackEmailCaptureSubmit(props: {
  form: Form; step: Step; tool?: string; outcome: Outcome; error_code?: ErrorCode;
}): void {
  trackConversionEvent('email_capture_submit', props);
}

export function trackWaitlistSubmit(props: { outcome: Outcome; error_code?: ErrorCode }): void {
  trackConversionEvent('waitlist_submit', props);
}

export function trackReadinessAssessmentSubmit(props: {
  outcome: Outcome; error_code?: ErrorCode; grade?: string;
}): void {
  trackConversionEvent('readiness_assessment_submit', props);
}

export function trackBookCallClick(placement: string, tool?: string): void {
  trackConversionEvent('book_call_click', { placement, tool });
}

export function trackContactFormSubmit(outcome: Outcome, error_code?: ErrorCode): void {
  trackConversionEvent('contact_form_submit', { outcome, error_code });
}

export function trackWebinarRegisterClick(webinarSlug: string, placement: string): void {
  trackConversionEvent('webinar_register_click', { webinar: webinarSlug, placement });
}
