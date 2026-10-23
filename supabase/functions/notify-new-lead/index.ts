import "jsr:@supabase/functions-js/edge-runtime.d.ts";

/**
 * notify-new-lead
 *
 * Called by a Supabase database webhook on INSERT to assessment_submissions.
 * verify_jwt is false because Supabase DB webhooks don't send JWTs.
 * Instead, we validate requests via a shared secret in the
 * X-Webhook-Secret header (set in Supabase webhook config).
 */

const NOTIFY_EMAIL = "1@christophersellers.com";
let cachedWebhookSecret = "";

async function getWebhookSecret() {
  const configured = Deno.env.get("WEBHOOK_SECRET");
  if (configured?.trim()) return configured;
  if (cachedWebhookSecret) return cachedWebhookSecret;

  const url = Deno.env.get("SUPABASE_URL");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !serviceRoleKey) return null;

  try {
    const response = await fetch(`${url.replace(/\/$/, "")}/rest/v1/rpc/get_notify_new_lead_secret`, {
      method: "POST",
      headers: {
        apikey: serviceRoleKey,
        Authorization: `Bearer ${serviceRoleKey}`,
        "Content-Type": "application/json",
      },
      body: "{}",
    });
    if (!response.ok) return null;
    const secret = await response.json();
    if (typeof secret !== "string" || !secret.trim()) return null;
    cachedWebhookSecret = secret;
    return secret;
  } catch {
    console.error("notify-new-lead: secret lookup failed");
    return null;
  }
}

async function secretsMatch(expected: string, incoming: string) {
  const encoder = new TextEncoder();
  const expectedDigest = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(expected)));
  const incomingDigest = new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(incoming)));
  let difference = 0;
  for (let i = 0; i < expectedDigest.length; i++) {
    difference |= expectedDigest[i] ^ incomingDigest[i];
  }
  return difference === 0;
}

Deno.serve(async (req: Request) => {
  // --- Request validation ---
  // Only accept POST
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
    const webhookSecret = await getWebhookSecret();
    if (!webhookSecret) {
      console.error("notify-new-lead: webhook secret is not configured");
      return new Response(JSON.stringify({ error: "Server misconfigured" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }

    const incomingSecret = req.headers.get("x-webhook-secret");
    if (!incomingSecret || !(await secretsMatch(webhookSecret, incomingSecret))) {
      console.error("notify-new-lead: invalid or missing webhook secret");
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }

    const payload = await req.json();
    const record = payload.record || payload;

    // Validate required fields exist
    if (!record || typeof record !== "object") {
      return new Response(JSON.stringify({ error: "Invalid payload" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const name = record.name || "Unknown";
    const email = record.email || "no-email";
    const company = record.company || "";
    const role = record.role || "";
    const source = record.source || "unknown";
    const isTestLead = payload.test === true || (typeof source === "string" && source.toLowerCase() === "test");
    const score = record.quiz_score;
    const grade = record.quiz_grade;

    const summary = [
      `New RegEngine Lead`,
      ``,
      `Name: ${name}`,
      `Email: ${email}`,
      `Company: ${company}`,
      `Role: ${role}`,
      `Tool: ${source}`,
      score !== null && score !== undefined ? `Score: ${score}` : null,
      grade ? `Grade: ${grade}` : null,
      ``,
      `Time: ${new Date().toISOString()}`,
    ].filter(Boolean).join("\n");

    // Try sending via Resend if API key is available
    const resendKey = Deno.env.get("RESEND_API_KEY");
    if (resendKey) {
      const emailRes = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${resendKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: "RegEngine <leads@regengine.co>",
          to: [NOTIFY_EMAIL],
          subject: `${isTestLead ? "[TEST] " : ""}New Lead: ${name} (${company}) via ${source}`,
          text: summary,
        }),
      });
      console.log("Resend response:", emailRes.status);
    } else {
      console.log("No RESEND_API_KEY set — notification not sent.");
    }

    return new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    console.error("notify-new-lead error:", err);
    return new Response(JSON.stringify({ ok: false, error: "Internal error" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
});
