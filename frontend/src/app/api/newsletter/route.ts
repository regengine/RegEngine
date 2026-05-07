import { NextRequest, NextResponse } from 'next/server';

/**
 * POST /api/newsletter
 * Minimal newsletter signup endpoint (#567).
 * Forwards the subscriber email to a mailing list provider when configured.
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

  const listEndpoint = process.env.NEWSLETTER_WEBHOOK_URL;
  if (!listEndpoint) {
    return NextResponse.json({ error: 'Newsletter signup is not configured yet' }, { status: 503 });
  }

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

  return NextResponse.json({ ok: true });
}
