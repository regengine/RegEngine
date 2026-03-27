/**
 * GET /api/admin/jwt-status
 *
 * Returns the current JWT key rotation status for operations monitoring.
 * Requires admin authentication via re_admin_key cookie or x-admin-key header.
 *
 * Response:
 *   - current_key_kid:    Key ID of the active signing key
 *   - current_key_age_days: Days since the current key was created (null if date not set)
 *   - previous_key_kid:   Key ID of the previous key (null if not configured)
 *   - previous_key_age_days: Days since the previous key was created (null if not set)
 *   - rotation_in_progress: Whether a previous key is still active
 *   - recommendation:     Actionable advice (e.g. "rotate" if key is older than 90 days)
 */

import { NextRequest, NextResponse } from 'next/server';
import { getSigningKey, getPreviousKey, rotateKey } from '@/lib/jwt-keys';

export const dynamic = 'force-dynamic';

const ROTATION_THRESHOLD_DAYS = 90;

function requireAdmin(request: NextRequest): boolean {
    // Check for admin key in cookie or header
    const adminKey =
        request.cookies.get('re_admin_key')?.value ||
        request.headers.get('x-admin-key');

    if (!adminKey) {
        return false;
    }

    // Verify it matches the server-side admin key
    const expectedAdminKey = process.env.ADMIN_API_KEY || process.env.REGENGINE_ADMIN_KEY;
    if (!expectedAdminKey) {
        // No admin key configured server-side — reject
        return false;
    }

    return adminKey === expectedAdminKey;
}

function daysSince(date: Date | null): number | null {
    if (!date) return null;
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    return Math.floor(diffMs / (1000 * 60 * 60 * 24));
}

export async function GET(request: NextRequest) {
    if (!requireAdmin(request)) {
        return NextResponse.json(
            { error: 'Unauthorized — admin credentials required' },
            { status: 401 },
        );
    }

    try {
        const currentKey = getSigningKey();
        const previousKey = getPreviousKey();

        const currentAgeDays = daysSince(currentKey.createdAt);
        const previousAgeDays = previousKey
            ? daysSince(previousKey.createdAt)
            : null;

        // Build recommendation
        let recommendation = 'Key configuration is healthy.';
        if (currentAgeDays !== null && currentAgeDays > ROTATION_THRESHOLD_DAYS) {
            recommendation =
                `Current key is ${currentAgeDays} days old (threshold: ${ROTATION_THRESHOLD_DAYS} days). ` +
                'Rotate the signing key soon.';
        } else if (currentAgeDays === null) {
            recommendation =
                'JWT_SIGNING_KEY_DATE is not set — unable to determine key age. ' +
                'Set it to track rotation schedule.';
        }

        if (previousKey) {
            recommendation +=
                ' Previous key is still active (rotation in progress). ' +
                'Remove JWT_PREVIOUS_KEY after max token lifetime (7 days).';
        }

        const { instructions } = rotateKey();

        return NextResponse.json({
            current_key_kid: currentKey.kid,
            current_key_created_at: currentKey.createdAt?.toISOString() ?? null,
            current_key_age_days: currentAgeDays,
            previous_key_kid: previousKey?.kid ?? null,
            previous_key_created_at: previousKey?.createdAt?.toISOString() ?? null,
            previous_key_age_days: previousAgeDays,
            rotation_in_progress: !!previousKey,
            rotation_threshold_days: ROTATION_THRESHOLD_DAYS,
            recommendation,
            rotation_instructions: instructions,
        });
    } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        return NextResponse.json(
            { error: `JWT key configuration error: ${message}` },
            { status: 500 },
        );
    }
}
