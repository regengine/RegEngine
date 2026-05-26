# Resend SMTP setup runbook

Unblocks cold email at volume (tracker #2352). Without Resend, you're
capped at LinkedIn InMail (25 credits remaining) and personal Gmail
sends (10–20/day before deliverability rep tanks).

Last updated: 2026-05-23

## Prereqs

- Cloudflare or Vercel DNS access for `regengine.co` (you have both)
- 10 minutes
- A credit card for Resend (free tier covers 100 emails/day, paid
  starts at $20/mo for 50k/mo — plenty for cold outbound)

## Step 1 — Resend signup

1. https://resend.com/signup — sign up with `chris.sellers01@gmail.com`
   (same account you use for Cloudflare so notifications consolidate)
2. Verify email
3. Skip the onboarding wizard if it appears

## Step 2 — Add domain

1. Resend dashboard → **Domains** → **Add Domain**
2. Domain: `regengine.co`
3. Region: **US East (Virginia)** — closest to Vercel default
4. Resend shows 3 DNS records to add:
   - `MX` record (mail routing)
   - `TXT` record for SPF (sender policy)
   - `TXT` record for DKIM (signing key)
5. Copy all three — leave the page open

## Step 3 — Add DNS records

Where is `regengine.co` DNS managed?

- **If Cloudflare:** dashboard → regengine.co → DNS → Records → Add
  record (3 times, one per Resend value)
- **If Vercel:** dashboard → Domains → regengine.co → DNS Records →
  Add record (3 times)

For each:
- **Type:** matches Resend (MX / TXT / TXT)
- **Name:** matches Resend (often `send.regengine.co` for the MX, root
  `@` or `resend._domainkey` for the TXTs)
- **Value:** paste from Resend exactly
- **TTL:** Auto / default
- **Proxied (Cloudflare only):** OFF for MX, OFF for TXT — these must
  resolve to Resend, not Cloudflare's proxy

## Step 4 — Verify in Resend

Back in the Resend Domains tab:

1. Click **Verify DNS Records** — usually takes 1–5 min for DNS to
   propagate
2. All 3 records turn green = ready
3. If they don't verify after 10 min, the most common cause is the TXT
   value got wrapped or had a stray space — re-paste from Resend

## Step 5 — Create API key

1. Resend → **API Keys** → **Create API Key**
2. Name: `regengine-prod-cold-outbound`
3. Permission: **Sending access**
4. Domain: `regengine.co` (scope it)
5. **Copy the key immediately — Resend only shows it once**

## Step 6 — Store in Railway

```bash
railway link --project RegEngine-Prod --environment production
railway service RegEngine
railway variables --set "RESEND_API_KEY=re_..."  # paste your key
```

(If you'd rather store it locally for outreach scripting only, drop
it in `~/.config/regengine/.env` and source it from your shell.)

## Step 7 — Smoke test

Send yourself a test email to confirm everything works:

```bash
curl -X POST https://api.resend.com/emails \
  -H "Authorization: Bearer $RESEND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "from": "Christopher <chris@regengine.co>",
    "to": "chris.sellers01@gmail.com",
    "subject": "Resend test",
    "text": "If you see this, regengine.co cold outbound is live."
  }'
```

Expected: 200 with an `id` in the response. Email lands in Gmail
within seconds. If it lands in spam, that's a domain-reputation
warmup issue — DKIM and SPF being green at Step 4 means it's *valid*
but reputation builds over a few weeks of legitimate sends.

## Sending pace once live

Even with Resend, don't blast 200/day on day 1. Inbox providers (Gmail,
Outlook) score new sending domains carefully:

| Week | Daily volume |
|---|---|
| 1 | 20–30/day |
| 2 | 50/day |
| 3 | 100/day |
| 4+ | 200+/day if reply/bounce rates are healthy |

Track bounce rate (should stay under 5%) and complaint rate (under
0.1%) in the Resend dashboard.

## What this unblocks

- **Wave 2 / Wave 3 outreach via email** if LinkedIn responses are
  thin
- **Member-services follow-ups** to IFPA / WGA after the first cold
  send
- **Pilot warm-up emails** for prospects who book a Calendly slot
  ("Looking forward to our call Wednesday — here's a 1-pager to skim
  beforehand")

## Rollback

If Resend mis-sends or you want to kill outbound:

1. Resend dashboard → API Keys → Revoke `regengine-prod-cold-outbound`
2. New keys can be issued at any time without DNS changes

The domain itself stays verified — only the key controls send ability.
