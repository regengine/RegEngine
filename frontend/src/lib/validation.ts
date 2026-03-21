/**
 * Shared validation utilities.
 *
 * Centralises common checks (email format, phone, etc.) so every form
 * uses the same rules instead of ad-hoc string checks.
 */

/** RFC-5322-ish email regex — catches the vast majority of invalid addresses. */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Returns `true` when the value looks like a plausible email address. */
export function isValidEmail(value: string): boolean {
    return EMAIL_RE.test(value.trim());
}
