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

Deno.serve(async (req: Request) => {
  // --- Request validation ---
  // Only accept POST
  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" },
    });
  }

  // A missing secret must never make this public endpoint accept requests.
  const webhookSecret = Deno.env.get("WEBHOOK_SECRET");
  if (!webhookSecret?.trim()) {
    console.error("notify-new-lead: WEBHOOK_SECRET is not configured");
    return new Response(JSON.stringify({ error: "Webhook authentication unavailable" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }

  const incomingSecret = req.headers.get("x-webhook-secret");
  if (incomingSecret !== webhookSecret) {
    console.error("notify-new-lead: invalid or missing webhook secret");
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  try {
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

    console.log(summary);

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
          subject: `New Lead: ${name} (${company}) via ${source}`,
          text: summary,
        }),
      });
      console.log("Resend response:", emailRes.status);
    } else {
      console.log("No RESEND_API_KEY set — lead logged only.");
    }

    return new Response(JSON.stringify({ ok: true, lead: email }), {
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    console.error("notify-new-lead error:", err);
    return new Response(JSON.stringify({ ok: false, error: String(err) }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
});
