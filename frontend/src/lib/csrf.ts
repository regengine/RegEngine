/**
 * CSRF Protection Utilities
 *
 * Stub — the actual implementation will land with the CSRF protection PR.
 * This file exists so the middleware import doesn't break the build.
 */

import type { NextRequest } from 'next/server';

export const CSRF_HEADER = 'x-csrf-token';
export const CSRF_SIG_COOKIE = 're_csrf_sig';
export const CSRF_PROTECTED_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Verify a CSRF token from the request headers against the signed cookie.
 * Returns true if the request is safe (GET/HEAD/OPTIONS) or the token is valid.
 */
export function verifyCsrfToken(_request: NextRequest): boolean {
  // Stub: always returns true until the full CSRF implementation lands.
  return true;
}
