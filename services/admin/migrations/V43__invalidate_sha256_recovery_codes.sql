-- V43: Invalidate legacy SHA-256 recovery code hashes (#1041)
--
-- hash_recovery_code() previously used hashlib.sha256 — a fast hash
-- attackable at GPU speed (~2^47.6 for 8-char alphanum codes). Recovery codes
-- are auth credentials and warrant the same protection as passwords.
--
-- As of this migration, hash_recovery_code() uses argon2id via passlib's
-- CryptContext(schemes=["argon2"]). Argon2 hashes start with "$argon2" so
-- any row whose code_hash does NOT start with "$argon2" is a legacy SHA-256
-- hex digest that can no longer be verified by the new implementation.
--
-- We explicitly delete those rows so affected users are prompted to regenerate
-- their recovery codes rather than silently failing to redeem them. Affected
-- users will see a "no valid recovery codes" error and must re-enroll MFA to
-- generate a fresh set of argon2-hashed codes.
--
-- This is a non-destructive change from a security standpoint: the old hashes
-- already fail verify_recovery_code() in the updated code (passlib raises on
-- unrecognized hash format), so this migration only makes the invalidation
-- explicit and visible in the database.

DELETE FROM admin_mfa_recovery_codes
WHERE code_hash NOT LIKE '$argon2%';

COMMENT ON TABLE admin_mfa_recovery_codes IS
    'One-time MFA recovery codes. code_hash must be an argon2id hash (prefix $argon2). Legacy SHA-256 hashes were removed in V43 (#1041).';
