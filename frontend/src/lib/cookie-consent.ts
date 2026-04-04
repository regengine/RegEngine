/**
 * Cookie consent helpers.
 *
 * Consent is stored in the `re_cookie_consent` cookie (not localStorage)
 * so it is sent to the server on every request and works across subdomains.
 *
 * Values: "accepted" | "declined"
 * TTL:    365 days
 */

export const CONSENT_COOKIE_NAME = 're_cookie_consent';
export type ConsentValue = 'accepted' | 'declined';

/** Read the stored consent value from document.cookie. Returns null if not yet set. */
export function getStoredConsent(): ConsentValue | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)re_cookie_consent=([^;]+)/);
  const raw = match?.[1];
  if (raw === 'accepted' || raw === 'declined') return raw;
  return null;
}

/** Persist the consent decision as a cookie. */
export function setConsentCookie(value: ConsentValue): void {
  if (typeof document === 'undefined') return;
  const maxAge = 365 * 24 * 60 * 60; // 1 year in seconds
  document.cookie = `${CONSENT_COOKIE_NAME}=${value}; max-age=${maxAge}; path=/; SameSite=Lax`;
}

/** Dispatch a DOM event to re-open the consent banner from anywhere (e.g. footer link). */
export function requestShowCookiePrefs(): void {
  if (typeof document !== 'undefined') {
    document.dispatchEvent(new CustomEvent('re:show-cookie-prefs'));
  }
}
