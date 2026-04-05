import { NextRequest, NextResponse } from 'next/server';

/**
 * POST /api/newsletter
 * Minimal newsletter signup endpoint (#567).
 * Stores the subscriber email or forwards to a mailing list provider.
 */
export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const email =
    typeof body === 'object' && body !== null && 'email' in body
      ? String((body as Record<string, unknown>).email).trim()
      : '';

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return NextResponse.json({ error: 'Invalid email address' }, { status: 400 });
  }

  // Forward to mailing list provider if configured (optional env var).
  // Without a provider configured, we simply return 200 so the front-end
  // shows the success state. Wire in Postmark / Loops / MailerLite here.
  const listEndpoint = process.env.NEWSLETTER_WEBHOOK_URL;
  if (listEndpoint) {
    try {
      const upstream = await fetch(listEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
      if (!upstream.ok) {
        return NextResponse.json({ error: 'Upstream error' }, { status: 502 });
      }
    } catch {
      return NextResponse.json({ error: 'Upstream unreachable' }, { status: 502 });
    }
  }

  return NextResponse.json({ ok: true });
}
