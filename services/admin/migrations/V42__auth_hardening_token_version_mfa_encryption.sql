-- V42: Auth hardening — token_version + encrypted mfa_secret migration
--
-- This migration supports three related auth-hardening fixes:
--   * #1349 — /auth/reset-password must revoke outstanding JWTs. We add
--     users.token_version (monotonically increasing integer). The JWT carries
--     the version at mint time, and get_current_user rejects tokens whose
--     embedded version no longer matches. Bumping the column invalidates every
--     outstanding access token for that user.
--   * #1375 — /logout-all reuses the same mechanism.
--   * #1376 — users.mfa_secret must be encrypted at rest. We add
--     mfa_secret_ciphertext (Fernet-encrypted) alongside the legacy plaintext
--     column. Existing rows stay readable by the legacy path until a one-shot
--     re-encryption tool copies them over; once the tool clears the plaintext
--     column, the legacy path is disabled in code.
--
-- All columns are additive and nullable, so this migration is safe on a live
-- database without locking writes.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;

-- Fernet ciphertext of the base32 TOTP seed. NULL => legacy plaintext still in
-- users.mfa_secret. Code prefers ciphertext when present.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS mfa_secret_ciphertext TEXT;

COMMENT ON COLUMN users.token_version IS
    'Monotonic counter. Bumped on password reset / logout-all to invalidate outstanding JWTs (#1349, #1375).';
COMMENT ON COLUMN users.mfa_secret_ciphertext IS
    'Fernet-encrypted TOTP seed. Falls back to users.mfa_secret if NULL (#1376). Requires MFA_ENCRYPTION_KEY env var.';
