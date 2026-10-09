/**
 * First-party client error beacon (WS-10).
 *
 * Receives sampled window.onerror / onunhandledrejection reports from
 * src/instrumentation-client.ts and writes them to server logs (picked up
 * by the platform log drain). This keeps the browser Sentry SDK out of the
 * client bundle — the original reason instrumentation-client.ts was a
 * no-op — while ending the "client errors vanish silently" gap.
 *
 * Privacy/abuse posture:
 *   - Payloads are PII-free by construction (the client strips query
 *     strings and sends no cookies/user identifiers), and this handler
 *     re-truncates every field server-side so a malicious caller cannot
 *     log-flood with megabyte strings.
 *   - Per-instance token bucket per client IP (best effort on serverless;
 *     each instance enforces independently) dampens bursts rather than
 *     enforcing a hard global cap. A distributed flood still reaches the
 *     log drain, so the logging pipeline must absorb it; the 429 below
 *     only tells well-behaved senders to back off.
 *   - Always responds 204 (or 429) with no body — the beacon is
 *     fire-and-forget and must never leak server state to the page.
 */
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';

const MAX_BODY_BYTES = 8 * 1024;
const MAX_MESSAGE_CHARS = 500;
const MAX_STACK_CHARS = 4000;
const MAX_URL_CHARS = 300;

// Token bucket: N reports per IP per window, per server instance.
const WINDOW_MS = 60_000;
const MAX_PER_WINDOW = 10;
const buckets = new Map<string, { count: number; windowStart: number }>();
const MAX_TRACKED_IPS = 10_000;

function allow(ip: string): boolean {
    const now = Date.now();
    const bucket = buckets.get(ip);
    if (!bucket || now - bucket.windowStart >= WINDOW_MS) {
        // Opportunistic cleanup so the map cannot grow unbounded.
        if (buckets.size >= MAX_TRACKED_IPS) {
            for (const [key, value] of buckets) {
                if (now - value.windowStart >= WINDOW_MS) buckets.delete(key);
            }
            if (buckets.size >= MAX_TRACKED_IPS) buckets.clear();
        }
        buckets.set(ip, { count: 1, windowStart: now });
        return true;
    }
    bucket.count += 1;
    return bucket.count <= MAX_PER_WINDOW;
}

function clip(value: unknown, max: number): string {
    if (typeof value !== 'string') return '';
    return value.slice(0, max);
}

function stripQuery(url: string): string {
    const cut = url.split(/[?#]/, 1)[0] ?? '';
    return cut;
}

export async function POST(request: NextRequest) {
    const ip =
        request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ||
        'unknown';
    if (!allow(ip)) {
        return new NextResponse(null, {
            status: 429,
            headers: { 'Retry-After': String(WINDOW_MS / 1000) },
        });
    }

    let payload: Record<string, unknown>;
    try {
        const raw = await request.text();
        if (raw.length > MAX_BODY_BYTES) {
            return new NextResponse(null, { status: 204 });
        }
        payload = JSON.parse(raw) as Record<string, unknown>;
    } catch {
        return new NextResponse(null, { status: 204 });
    }

    const kind = payload.kind === 'unhandledrejection' ? 'unhandledrejection' : 'error';
    const entry = {
        kind,
        message: clip(payload.message, MAX_MESSAGE_CHARS),
        stack: clip(payload.stack, MAX_STACK_CHARS),
        // Query strings are stripped client-side already; strip again here
        // so a hand-crafted payload cannot smuggle tokens into logs.
        url: stripQuery(clip(payload.url, MAX_URL_CHARS)),
        release: clip(payload.release, 64),
    };

    if (!entry.message) {
        return new NextResponse(null, { status: 204 });
    }

    // Structured single-line record for the platform log drain.
    console.error('[client-error]', JSON.stringify(entry));

    return new NextResponse(null, { status: 204 });
}
