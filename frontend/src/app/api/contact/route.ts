import { NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

interface ContactPayload {
  name?: string;
  email?: string;
  company?: string;
  message?: string;
}

export async function POST(request: Request) {
  let payload: ContactPayload;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  const { name, email, message } = payload;
  if (!name?.trim() || !email?.trim() || !message?.trim()) {
    return NextResponse.json({ error: 'missing_fields' }, { status: 400 });
  }

  const webhook = process.env.CONTACT_WEBHOOK_URL;
  if (!webhook) {
    return NextResponse.json(
      { error: 'contact_webhook_unconfigured' },
      { status: 503 },
    );
  }

  try {
    const res = await fetch(webhook, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: 'regengine.co/contact',
        received_at: new Date().toISOString(),
        ...payload,
      }),
    });
    if (!res.ok) {
      return NextResponse.json({ error: 'webhook_failed' }, { status: 502 });
    }
  } catch {
    return NextResponse.json({ error: 'webhook_unreachable' }, { status: 502 });
  }

  return NextResponse.json({ ok: true });
}
