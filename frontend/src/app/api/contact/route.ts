/**
 * /api/contact — Marketing site contact-form handler.
 *
 * Origin: mythos cleanup. The /contact page promises "We'll respond within
 * one business day," so this route must actually capture submissions even
 * when external infra is unconfigured. Previously this handler returned 503
 * whenever CONTACT_WEBHOOK_URL was unset, silently breaking the promise on
 * any environment that hadn't been bootstrapped.
 *
 * Behaviour:
 *   1. Validate payload (name, email, message required; email regex-checked).
 *   2. If CONTACT_WEBHOOK_URL is set, forward to it (Zapier/Make/n8n/etc).
 *   3. Always log a structured line to stdout so submissions are recoverable
 *      from Vercel function logs even when no provider is wired.
 *   4. Return 200 {ok:true} on success.
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
}

// Pragmatic email regex — rejects obvious garbage, accepts anything that
// looks plausible. Final delivery is the real validator.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const DESTINATION = 'chris@regengine.co';

export async function POST(request: Request) {
  let payload: ContactPayload;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
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
    source: 'regengine.co/contact',
    destination: DESTINATION,
    received_at: new Date().toISOString(),
    name,
    email,
    company,
    message,
  };

  // Always log so submissions are never lost, even if the webhook is unset
  // or fails. Vercel captures stdout in function logs.
  // TODO: wire to real email provider (Resend) so we don't depend on log scraping.
  console.info('[contact] submission', JSON.stringify(submission));

  const webhook = process.env.CONTACT_WEBHOOK_URL;
  if (webhook) {
    try {
      const res = await fetch(webhook, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(submission),
      });
      if (!res.ok) {
        console.error('[contact] webhook responded non-2xx', res.status);
        // Don't 502 the user — we already logged the submission. Soft-success.
      }
    } catch (err) {
      console.error('[contact] webhook unreachable', err);
      // Same — soft-success. Submission is recoverable from logs.
    }
  } else {
    console.warn('[contact] CONTACT_WEBHOOK_URL is unset; submission only logged');
  }

  return NextResponse.json({ ok: true });
}
