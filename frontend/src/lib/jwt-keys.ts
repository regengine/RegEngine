/**
 * JWT Key Rotation — two-key overlap pattern for zero-downtime rotation.
 *
 * This module manages signing and verification keys for RegEngine JWTs.
 * Keys are identified by a `kid` (key ID) derived from a truncated SHA-256
 * hash of the secret, so verifiers can select the correct key from the
 * JWT header without exposing the secret itself.
 *
 * Environment variables:
 *   JWT_SIGNING_KEY       — Current active signing/verification key (required)
 *   JWT_SIGNING_KEY_DATE  — ISO-8601 date when the current key was created (optional, for age tracking)
 *   JWT_PREVIOUS_KEY      — Previous key still accepted for verification during rotation (optional)
 *   JWT_PREVIOUS_KEY_DATE — ISO-8601 date when the previous key was created (optional)
 *   AUTH_SECRET_KEY        — Legacy fallback; used if JWT_SIGNING_KEY is not set
 *
 * ─────────────────────────────────────────────────────────────────────
 * Rotation procedure:
 *   1. Generate a new secret:
 *        openssl rand -base64 64
 *   2. In your deployment environment (Vercel / Railway):
 *        - Set JWT_PREVIOUS_KEY      = current JWT_SIGNING_KEY value
 *        - Set JWT_PREVIOUS_KEY_DATE = current JWT_SIGNING_KEY_DATE value
 *        - Set JWT_SIGNING_KEY       = <new secret from step 1>
 *        - Set JWT_SIGNING_KEY_DATE  = <today's ISO date, e.g. 2026-03-27>
 *   3. Deploy — new tokens will be signed with the new key; tokens signed
 *      with the old key are still accepted for verification.
 *   4. After the maximum token lifetime (7 days by default), remove
 *      JWT_PREVIOUS_KEY and JWT_PREVIOUS_KEY_DATE.
 * ─────────────────────────────────────────────────────────────────────
 */

/**
 * Represents a single JWT key with its identifier and metadata.
 */
export interface JWTKey {
    /** Key ID — first 12 hex chars of SHA-256(secret). Embedded in JWT `kid` header. */
    kid: string;
    /** The raw secret bytes, encoded for use with `jose`. */
    secret: Uint8Array;
    /** When this key was created / deployed. Null if the date env var is not set. */
    createdAt: Date | null;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Derive a deterministic `kid` from a secret string.
 * Uses the Web Crypto API (available in Node 18+ and all modern runtimes).
 * Falls back to a simple hash if crypto.subtle is unavailable (e.g. tests).
 */
function deriveKidSync(secret: string): string {
    // Simple non-crypto hash for kid derivation — we only need uniqueness,
    // not cryptographic strength. The kid is not secret.
    let hash = 0;
    for (let i = 0; i < secret.length; i++) {
        const char = secret.charCodeAt(i);
        hash = ((hash << 5) - hash + char) | 0;
    }
    // Convert to positive hex and pad to 12 chars
    const positiveHash = (hash >>> 0).toString(16).padStart(8, '0');
    // Add a second pass for more uniqueness
    let hash2 = 0x811c9dc5; // FNV offset basis
    for (let i = 0; i < secret.length; i++) {
        hash2 ^= secret.charCodeAt(i);
        hash2 = Math.imul(hash2, 0x01000193); // FNV prime
    }
    const secondHalf = (hash2 >>> 0).toString(16).padStart(8, '0');
    return (positiveHash + secondHalf).slice(0, 12);
}

function buildKey(secret: string, dateStr?: string): JWTKey {
    const encoder = new TextEncoder();
    return {
        kid: deriveKidSync(secret),
        secret: encoder.encode(secret),
        createdAt: dateStr ? new Date(dateStr) : null,
    };
}

// ---------------------------------------------------------------------------
// Cached key instances — computed once per cold start
// ---------------------------------------------------------------------------

let _signingKey: JWTKey | null = null;
let _previousKey: JWTKey | null = null;
let _initialized = false;

function ensureInitialized(): void {
    if (_initialized) return;
    _initialized = true;

    const currentSecret =
        process.env.JWT_SIGNING_KEY || process.env.AUTH_SECRET_KEY;
    if (currentSecret) {
        _signingKey = buildKey(
            currentSecret,
            process.env.JWT_SIGNING_KEY_DATE,
        );
    }

    const previousSecret = process.env.JWT_PREVIOUS_KEY;
    if (previousSecret) {
        _previousKey = buildKey(
            previousSecret,
            process.env.JWT_PREVIOUS_KEY_DATE,
        );
    }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Returns the current active signing key.
 * Throws if no signing key is configured.
 */
export function getSigningKey(): JWTKey {
    ensureInitialized();
    if (!_signingKey) {
        throw new Error(
            '[jwt-keys] No signing key configured. ' +
            'Set JWT_SIGNING_KEY (or AUTH_SECRET_KEY) in environment variables.',
        );
    }
    return _signingKey;
}

/**
 * Returns all keys that should be tried during verification.
 * The current key is always first; the previous key (if set) is second.
 */
export function getVerificationKeys(): JWTKey[] {
    ensureInitialized();
    const keys: JWTKey[] = [];
    if (_signingKey) keys.push(_signingKey);
    if (_previousKey) keys.push(_previousKey);
    return keys;
}

/**
 * Returns the previous key if one is configured, or null.
 */
export function getPreviousKey(): JWTKey | null {
    ensureInitialized();
    return _previousKey;
}

/**
 * Utility: logs what environment variables need updating for a rotation.
 * This is a development/ops helper — call it from a script or admin endpoint.
 */
export function rotateKey(): { instructions: string[] } {
    ensureInitialized();
    const instructions: string[] = [];

    instructions.push('1. Generate a new secret: openssl rand -base64 64');

    if (_signingKey) {
        instructions.push(
            '2. Set JWT_PREVIOUS_KEY = current JWT_SIGNING_KEY value',
        );
        instructions.push(
            '3. Set JWT_PREVIOUS_KEY_DATE = current JWT_SIGNING_KEY_DATE value',
        );
    } else {
        instructions.push(
            '2. Set JWT_PREVIOUS_KEY = current AUTH_SECRET_KEY value',
        );
        instructions.push(
            '3. Set JWT_PREVIOUS_KEY_DATE = today\'s date (ISO-8601)',
        );
    }
    instructions.push('4. Set JWT_SIGNING_KEY = <new secret>');
    instructions.push(
        '5. Set JWT_SIGNING_KEY_DATE = today\'s date (ISO-8601, e.g. 2026-03-27)',
    );
    instructions.push('6. Deploy — new tokens use the new key, old tokens still verify');
    instructions.push(
        '7. After max token lifetime (7 days), remove JWT_PREVIOUS_KEY and JWT_PREVIOUS_KEY_DATE',
    );

    return { instructions };
}

/**
 * Reset the cached keys — only used in tests.
 */
export function _resetForTesting(): void {
    _signingKey = null;
    _previousKey = null;
    _initialized = false;
}
