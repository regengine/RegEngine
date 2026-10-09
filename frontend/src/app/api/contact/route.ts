/**
 * /api/contact — Marketing site contact-form handler.
 *
 * Behaviour:
 *   1. Validate payload (name, email, message required; email regex-checked).
 *   2. Require CONTACT_WEBHOOK_URL and forward without following redirects.
 *   3. Log only a generated event ID and non-PII delivery metadata.
 *   4. Return 200 only after the configured provider accepts the submission.
 *
 * TODO: wire to a real email provider (Resend most likely — already listed
 * as a subprocessor in /dpa). Target inbox: chris@regengine.co.
 */
import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

interface ContactPayload {
  name?: string;
  email?: string;
  company?: string;
  message?: string;
  // Honeypot — humans never see or fill this; bots that auto-fill every field
  // trip it. Rendered as a visually-hidden input by the contact form.
  website?: string;
}

// Pragmatic email regex — rejects obvious garbage, accepts anything that
// looks plausible. Final delivery is the real validator.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const DESTINATION = 'chris@regengine.co';

// Best-effort in-memory per-IP throttle. On serverless this is per-instance
// (not shared across function instances), so it dampens bursts rather than
// enforcing a hard global cap. A distributed flood still gets through to the
// webhook below, so the receiving provider must enforce its own cap; when it
// answers 429 this handler relays that backpressure instead of masking it.
// A durable shared store (Vercel KV / Upstash) would be the real fix for a
// global cap. Combined with the honeypot this raises abuse cost.
const RATE_LIMIT = 5;
const RATE_WINDOW_MS = 10 * 60 * 1000; // 10 minutes
// Bound so rotating source IPs cannot grow process memory without limit.
const MAX_TRACKED_IPS = 10_000;
const _hits = new Map<string, number[]>();

function clientIp(request: Request): string {
  const xff = request.headers.get('x-forwarded-for');
  if (xff) return xff.split(',')[0].trim();
  return request.headers.get('x-real-ip') || 'unknown';
}

function pruneExpired(now: number): void {
  for (const [key, times] of _hits) {
    const latest = times[times.length - 1];
    if (latest === undefined || now - latest >= RATE_WINDOW_MS) {
      _hits.delete(key);
    }
  }
  if (_hits.size >= MAX_TRACKED_IPS) _hits.clear();
}

function isRateLimited(ip: string, now: number): boolean {
  const recent = (_hits.get(ip) ?? []).filter((t) => now - t < RATE_WINDOW_MS);
  if (recent.length >= RATE_LIMIT) {
    _hits.set(ip, recent);
    return true;
  }
  // Opportunistic cleanup so the map cannot grow unbounded when callers
  // rotate source IPs. Mirrors the bound in api/client-errors.
  if (!_hits.has(ip) && _hits.size >= MAX_TRACKED_IPS) {
    pruneExpired(now);
  }
  recent.push(now);
  _hits.set(ip, recent);
  return false;
}

// Relay provider backpressure as-is (bounded) so a downstream cap that a
// distributed flood trips is visible to the caller as "slow down".
function providerRetryAfter(value: string | null): string {
  if (value !== null && /^\d+$/.test(value.trim())) {
    return String(Math.min(Math.max(parseInt(value.trim(), 10), 1), 3600));
  }
  return '60';
}

export async function POST(request: Request) {
  let payload: ContactPayload;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  // Honeypot: pretend success so we don't reveal the trap, but drop it.
  if ((payload.website ?? '').trim() !== '') {
    return NextResponse.json({ ok: true });
  }

  if (isRateLimited(clientIp(request), Date.now())) {
    return NextResponse.json(
      { error: 'rate_limited', detail: 'Too many submissions. Please try again later.' },
      { status: 429, headers: { 'Retry-After': '600' } },
    );
  }

  const name = payload.name?.trim() ?? '';
  const email = payload.email?.trim() ?? '';
  const company = payload.company?.trim() ?? '';
  const message = payload.message?.trim() ?? '';

  if (!name || !email || !message) {
    return NextResponse.json(
      { error: 'missing_fields', detail: 'name, email, and message are required' },
      { status: 400 },
    );
  }
  if (!EMAIL_RE.test(email)) {
    return NextResponse.json(
      { error: 'invalid_email', detail: 'email address is not well-formed' },
      { status: 400 },
    );
  }

  const submission = {
    submission_id: crypto.randomUUID(),
    source: 'regengine.co/contact',
    destination: DESTINATION,
    received_at: new Date().toISOString(),
    name,
    email,
    company,
    message,
  };

  // Never write contact content or identity to platform logs. The provider is
  // the system of record; logs carry only a correlation handle and shape.
  console.warn('[contact] submission_received', {
    submissionId: submission.submission_id,
    hasCompany: Boolean(company),
    messageLength: message.length,
  });

  const webhook = process.env.CONTACT_WEBHOOK_URL;
  if (!webhook) {
    console.error('[contact] delivery_unavailable', {
      submissionId: submission.submission_id,
      reason: 'webhook_not_configured',
    });
    return NextResponse.json(
      { error: 'contact_service_unavailable' },
      { status: 503 },
    );
  }

  try {
    const res = await fetch(webhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(submission),
      redirect: 'manual',
    });
    if (res.status >= 300 && res.status < 400) {
      console.error('[contact] delivery_refused', {
        submissionId: submission.submission_id,
        reason: 'redirect',
      });
      return NextResponse.json({ error: 'contact_delivery_failed' }, { status: 502 });
    }
    if (res.status === 429) {
      console.error('[contact] delivery_refused', {
        submissionId: submission.submission_id,
        reason: 'provider_rate_limited',
      });
      return NextResponse.json(
        { error: 'rate_limited', detail: 'Too many submissions. Please try again later.' },
        { status: 429, headers: { 'Retry-After': providerRetryAfter(res.headers.get('Retry-After')) } },
      );
    }
    if (!res.ok) {
      console.error('[contact] delivery_refused', {
        submissionId: submission.submission_id,
        status: res.status,
      });
      return NextResponse.json({ error: 'contact_delivery_failed' }, { status: 502 });
    }
  } catch (error) {
    console.error('[contact] delivery_unavailable', {
      submissionId: submission.submission_id,
      errorClass: error instanceof Error ? error.name : 'UnknownError',
    });
    return NextResponse.json({ error: 'contact_service_unavailable' }, { status: 503 });
  }

  return NextResponse.json({ ok: true });
}
