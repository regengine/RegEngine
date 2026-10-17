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
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
}

function utmValue(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  return value.trim().toLowerCase().slice(0, 100) || null;
}

// Pragmatic email regex — rejects obvious garbage, accepts anything that
// looks plausible. Final delivery is the real validator.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const DESTINATION = 'chris@regengine.co';

// Best-effort in-memory per-IP throttle. On serverless this is per-instance
// (not shared across Vercel function instances), so it dampens bursts rather
// than enforcing a hard global cap — a durable store (Vercel KV / Upstash)
// would be the real fix. Combined with the honeypot it raises abuse cost.
const RATE_LIMIT = 5;
const RATE_WINDOW_MS = 10 * 60 * 1000; // 10 minutes
const _hits = new Map<string, number[]>();

function clientIp(request: Request): string {
  const xff = request.headers.get('x-forwarded-for');
  if (xff) return xff.split(',')[0].trim();
  return request.headers.get('x-real-ip') || 'unknown';
}

function isRateLimited(ip: string, now: number): boolean {
  const recent = (_hits.get(ip) ?? []).filter((t) => now - t < RATE_WINDOW_MS);
  if (recent.length >= RATE_LIMIT) {
    _hits.set(ip, recent);
    return true;
  }
  recent.push(now);
  _hits.set(ip, recent);
  return false;
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
    utm_source: utmValue(payload.utm_source),
    utm_medium: utmValue(payload.utm_medium),
    utm_campaign: utmValue(payload.utm_campaign),
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
