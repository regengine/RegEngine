/**
 * Proxy sanitization tests.
 *
 * Covers the path-segment validators used by all catch-all and named-segment
 * proxy routes under src/app/api/**. These helpers sit between user input
 * (the dynamic segments of the proxy URL) and the backend fetch — a bug here
 * is a direct path-traversal / injection to the backend, so regressions must
 * be caught at unit-test time.
 *
 * Related fixes:
 *   #1152 — controls proxy skipped path sanitization
 *   #1152-follow-on — UUID validation on [tenantId]/[snapshotId] routes
 */

import { describe, it, expect } from 'vitest';
import { sanitizePath, validateUuid, safeSegment } from '@/lib/api-proxy';

describe('sanitizePath (catch-all [...path] proxies)', () => {
    it('joins valid path segments with slashes', () => {
        expect(sanitizePath(['api', 'v1', 'compliance'])).toBe('api/v1/compliance');
    });

    it('accepts alphanumeric, hyphen, underscore, dot, and slash', () => {
        expect(sanitizePath(['my-tenant_1.0', 'endpoint'])).toBe('my-tenant_1.0/endpoint');
    });

    it('rejects empty input', () => {
        expect(sanitizePath([])).toBeNull();
    });

    it('rejects traversal attempts with ../', () => {
        expect(sanitizePath(['..', 'admin', 'key'])).toBeNull();
        expect(sanitizePath(['foo', '..', 'bar'])).toBeNull();
    });

    it('rejects null-byte injection', () => {
        expect(sanitizePath(['foo\0bar'])).toBeNull();
    });

    it('rejects path segments with disallowed chars', () => {
        expect(sanitizePath(['foo bar'])).toBeNull();     // space
        expect(sanitizePath(['foo?bar'])).toBeNull();     // query injection
        expect(sanitizePath(['foo#bar'])).toBeNull();     // fragment injection
        expect(sanitizePath(['foo<script>'])).toBeNull(); // angle brackets
        expect(sanitizePath(['foo%2e%2e'])).toBeNull();   // % is not allowed
        expect(sanitizePath(['foo;bar'])).toBeNull();     // shell metachar
    });
});

describe('validateUuid (named [tenantId]/[snapshotId] proxies)', () => {
    it('accepts lowercase UUID v4', () => {
        const u = '6ba7b810-9dad-41d1-a0b4-00c04fd430c8';
        expect(validateUuid(u)).toBe(u);
    });

    it('normalizes uppercase UUIDs to lowercase', () => {
        expect(validateUuid('6BA7B810-9DAD-41D1-A0B4-00C04FD430C8')).toBe(
            '6ba7b810-9dad-41d1-a0b4-00c04fd430c8',
        );
    });

    it('rejects path-traversal payloads', () => {
        expect(validateUuid('../admin/key')).toBeNull();
        expect(validateUuid('..%2fadmin')).toBeNull();
        expect(validateUuid('6ba7b810-9dad-41d1-a0b4-00c04fd430c8/../admin')).toBeNull();
    });

    it('rejects malformed UUIDs', () => {
        expect(validateUuid('not-a-uuid')).toBeNull();
        expect(validateUuid('')).toBeNull();
        expect(validateUuid('6ba7b810-9dad-41d1-a0b4-00c04fd430c')).toBeNull();   // too short
        expect(validateUuid('6ba7b810-9dad-41d1-a0b4-00c04fd430c8X')).toBeNull(); // extra char
    });

    it('rejects null and undefined', () => {
        expect(validateUuid(null)).toBeNull();
        expect(validateUuid(undefined)).toBeNull();
    });

    it('rejects the nil UUID (v0) — not a real tenant', () => {
        expect(validateUuid('00000000-0000-0000-0000-000000000000')).toBeNull();
    });

    it('rejects UUIDs with injected control chars', () => {
        // eslint-disable-next-line no-control-regex
        expect(validateUuid('6ba7b810-9dad-41d1-a0b4-00c04fd430c8\r\n')).toBeNull();
    });
});

describe('safeSegment (general-purpose path segment encoder)', () => {
    it('encodes a plain segment unchanged', () => {
        expect(safeSegment('hello')).toBe('hello');
    });

    it('percent-encodes reserved chars', () => {
        expect(safeSegment('hello world')).toBe('hello%20world');
        expect(safeSegment('foo@bar.com')).toBe('foo%40bar.com');
    });

    it('rejects path separators', () => {
        expect(safeSegment('foo/bar')).toBeNull();
        expect(safeSegment('foo\\bar')).toBeNull();
    });

    it('rejects dot-dot traversal', () => {
        expect(safeSegment('..')).toBeNull();
        expect(safeSegment('.')).toBeNull();
    });

    it('rejects null byte and control chars', () => {
        expect(safeSegment('foo\0bar')).toBeNull();
        expect(safeSegment('foo\nbar')).toBeNull();
    });

    it('rejects oversized input', () => {
        expect(safeSegment('a'.repeat(257))).toBeNull();
    });

    it('rejects null/undefined', () => {
        expect(safeSegment(null)).toBeNull();
        expect(safeSegment(undefined)).toBeNull();
        expect(safeSegment('')).toBeNull();
    });
});

describe('URL shape: forwarded URLs for malicious input should not include the attack', () => {
    // These assertions document the intended behavior: the proxy builds the
    // upstream URL only after validation, so a malicious input never reaches
    // the fetch() call. We simulate the proxy's decision by running
    // validateUuid and asserting nothing survives that could escape the path.
    const maliciousInputs = [
        '../../admin/key',
        '../../../etc/passwd',
        'valid-looking-6ba7b810-9dad-41d1-a0b4-00c04fd430c8/../admin',
        '%2e%2e%2fadmin',
        'foo?tenant=other',
    ];

    for (const input of maliciousInputs) {
        it(`blocks "${input}"`, () => {
            expect(validateUuid(input)).toBeNull();
        });
    }

    it('forwards a valid UUID as-is (no injection in interpolation)', () => {
        const u = '6ba7b810-9dad-41d1-a0b4-00c04fd430c8';
        const validated = validateUuid(u);
        const forwardedUrl = `https://api.example.com/v1/compliance/snapshots/${validated}`;
        expect(forwardedUrl).toBe(
            'https://api.example.com/v1/compliance/snapshots/6ba7b810-9dad-41d1-a0b4-00c04fd430c8',
        );
    });
});
