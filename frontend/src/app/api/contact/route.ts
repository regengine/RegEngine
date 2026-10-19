/**
 * /api/contact — Marketing site contact-form handler.
 *
 * Behaviour:
 *   1. Validate payload (name, email, message required; email regex-checked).
 *   2. Deliver in order: CONTACT_WEBHOOK_URL (no redirect following), then
 *      Resend email to christopher@regengine.co when RESEND_API_KEY is set.
 *   3. Log only a generated event ID and non-PII delivery metadata.
 *   4. Return 200 only after the configured provider accepts the submission.
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
  source?: string;
}

function submissionSource(value: unknown): string {
  return value === 'signup' ? 'regengine.co/signup' : 'regengine.co/contact';
}

function utmValue(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  return value.trim().toLowerCase().slice(0, 100) || null;
}

// Pragmatic email regex — rejects obvious garbage, accepts anything that
// looks plausible. Final delivery is the real validator.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const DESTINATION = 'christopher@regengine.co';
const RESEND_EMAILS_URL = 'https://api.resend.com/emails';
const RESEND_TIMEOUT_MS = 10_000;
const SUBJECT_MAX_CHARS = 150;
const DEFAULT_RESEND_FROM = 'RegEngine <onboarding@regengine.co>';

function requestSubject(company: string, name: string): string {
  return `RegEngine request: ${company || name}`
    .replace(/[\r\n]/g, '')
    .slice(0, SUBJECT_MAX_CHARS);
}

function submissionText(submission: {
  submission_id: string;
  source: string;
  received_at: string;
  name: string;
  email: string;
  company: string;
  message: string;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
}): string {
  return [
    `submission_id: ${submission.submission_id}`,
    `source: ${submission.source}`,
    `received_at: ${submission.received_at}`,
    `name: ${submission.name}`,
    `email: ${submission.email}`,
    `company: ${submission.company}`,
    `utm_source: ${submission.utm_source ?? ''}`,
    `utm_medium: ${submission.utm_medium ?? ''}`,
    `utm_campaign: ${submission.utm_campaign ?? ''}`,
    `message: ${submission.message}`,
  ].join('\n');
}

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
    source: submissionSource(payload.source),
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
  if (webhook) {
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
          provider: 'webhook',
          reason: 'redirect',
        });
        return NextResponse.json({ error: 'contact_delivery_failed' }, { status: 502 });
      }
      if (!res.ok) {
        console.error('[contact] delivery_refused', {
          submissionId: submission.submission_id,
          provider: 'webhook',
          status: res.status,
        });
        return NextResponse.json({ error: 'contact_delivery_failed' }, { status: 502 });
      }
    } catch (error) {
      console.error('[contact] delivery_unavailable', {
        submissionId: submission.submission_id,
        provider: 'webhook',
        errorClass: error instanceof Error ? error.name : 'UnknownError',
      });
      return NextResponse.json({ error: 'contact_service_unavailable' }, { status: 503 });
    }

    return NextResponse.json({ ok: true });
  }

  if (!process.env.RESEND_API_KEY) {
    console.error('[contact] delivery_unavailable', {
      submissionId: submission.submission_id,
      reason: 'no_delivery_provider_configured',
    });
    return NextResponse.json(
      { error: 'contact_service_unavailable' },
      { status: 503 },
    );
  }

  try {
    const res = await fetch(RESEND_EMAILS_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${process.env.RESEND_API_KEY}`,
        'Content-Type': 'application/json',
      },
      redirect: 'manual',
      signal: AbortSignal.timeout(RESEND_TIMEOUT_MS),
      body: JSON.stringify({
        from: process.env.RESEND_FROM_EMAIL || DEFAULT_RESEND_FROM,
        to: [DESTINATION],
        reply_to: email,
        subject: requestSubject(company, name),
        text: submissionText(submission),
      }),
    });
    if (!res.ok) {
      console.error('[contact] delivery_refused', {
        submissionId: submission.submission_id,
        provider: 'resend',
        status: res.status,
      });
      return NextResponse.json({ error: 'contact_delivery_failed' }, { status: 502 });
    }
  } catch (error) {
    console.error('[contact] delivery_unavailable', {
      submissionId: submission.submission_id,
      provider: 'resend',
      errorClass: error instanceof Error ? error.name : 'UnknownError',
    });
    return NextResponse.json({ error: 'contact_service_unavailable' }, { status: 503 });
  }

  console.warn('[contact] delivered', {
    submissionId: submission.submission_id,
    provider: 'resend',
  });
  return NextResponse.json({ ok: true });
}
