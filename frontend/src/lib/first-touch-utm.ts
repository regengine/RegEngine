import { getStoredConsent } from './cookie-consent';

/**
 * First-touch UTM attribution for PostHog (AN1). The first URL in this tab that carries any
 * utm_* key sets the whole set; later URLs never replace it. Before Accept the values stay in
 * memory only, keeping the cookieless promise (A-2138). After Accept they are copied to
 * sessionStorage so a full reload in the same tab keeps first touch.
 */
export const FIRST_TOUCH_UTM_KEYS = [
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
] as const;
export type FirstTouchUtmKey = typeof FIRST_TOUCH_UTM_KEYS[number];
export type FirstTouchUtm = Partial<Record<FirstTouchUtmKey, string>>;

export const UTM_MAX_LENGTH = 128;
export const FIRST_TOUCH_STORAGE_KEY = 're_first_touch_utm';
const UTM_LABEL = /^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$/i;
const UTM_SOURCE_LABEL = /^[a-z0-9](?:[a-z0-9_.-]*[a-z0-9])?$/i;
const PHONE_SHAPE = /\d{3}[-_. ]\d{3}[-_. ]\d{4}/;

let firstTouch: FirstTouchUtm | null = null;

/** Caps at 128 characters, then allows only label-shaped values; free text, emails and phone-like values are dropped. */
export function cleanUtmValue(key: FirstTouchUtmKey, value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  const capped = value.trim().slice(0, UTM_MAX_LENGTH);
  const pattern = key === 'utm_source' ? UTM_SOURCE_LABEL : UTM_LABEL;
  if (!pattern.test(capped) || /\d{7,}/.test(capped) || PHONE_SHAPE.test(capped)) return undefined;
  return capped;
}

function cleanUtm(read: (key: FirstTouchUtmKey) => unknown): FirstTouchUtm {
  const result: FirstTouchUtm = {};
  for (const key of FIRST_TOUCH_UTM_KEYS) {
    const value = cleanUtmValue(key, read(key));
    if (value) result[key] = value;
  }
  return result;
}

function readStored(): FirstTouchUtm | null {
  try {
    const raw = window.sessionStorage.getItem(FIRST_TOUCH_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    const stored = cleanUtm((key) => (parsed as Record<string, unknown>)[key]);
    return Object.keys(stored).length ? stored : null;
  } catch {
    return null;
  }
}

function persistIfConsented(): void {
  if (!firstTouch || getStoredConsent() !== 'accepted') return;
  try {
    window.sessionStorage.setItem(FIRST_TOUCH_STORAGE_KEY, JSON.stringify(firstTouch));
  } catch {
    // Storage can be disabled; the in-memory first touch still applies in this tab.
  }
}

/** Records first touch from the current URL if none exists yet, and returns it. */
export function getFirstTouchUtm(): FirstTouchUtm {
  if (typeof window === 'undefined') return {};
  if (!firstTouch) firstTouch = readStored();
  if (!firstTouch) {
    const params = new URLSearchParams(window.location.search);
    const landing = cleanUtm((key) => params.get(key));
    if (Object.keys(landing).length) firstTouch = landing;
  }
  persistIfConsented();
  return firstTouch ? { ...firstTouch } : {};
}

/** Used on Decline: forget first touch in memory and storage. */
export function clearFirstTouchUtm(): void {
  firstTouch = null;
  try {
    window.sessionStorage.removeItem(FIRST_TOUCH_STORAGE_KEY);
  } catch {
    // Nothing to clear when storage is unavailable.
  }
}
